#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build station catalogs from configured media directories and select programs, commercials, and bumps
to fill scheduled blocks.
"""
import os
import sys
import random
import logging
import os.path
import datetime

from fs42.core.timings import DAYS
from fs42.core.timings import MIN_5
from fs42.tools.catalog import hint_agent
from fs42.tools.catalog import catalog_api
from fs42.tools.schedule import slot_reader
from fs42.tools.media import media_processor
from fs42.tools.sequence import sequence_api
from fs42.tools.catalog import autobump_agent
from fs42.core import logger as project_logger
from fs42.tools.catalog._constants import COLORS
from fs42.tools.schedule.liquid_blocks import ReelBlock
from fs42.tools.catalog.catalog_entry import CatalogEntry
from fs42.tools.catalog._constants import FF_USE_CATAGLOG_DB
from fs42.tools.catalog._constants import FF_USE_FLUID_FILE_CACHE
from fs42.tools.catalog.catalog_entry import NoFillerContentFound
from fs42.tools.catalog.catalog_entry import MatchingContentNotFound

_logger = project_logger.setup('fs42.tools.catalog.catalog')

try:
    try:
        # try to import from version > 2.0
        from moviepy import VideoFileClip
    except ImportError:
        # fall back to import from version 1.0
        from moviepy.editor import VideoFileClip  # type: ignore
except ImportError:
    # moviepy not installed at all - it's only used as a fallback duration
    # probe when ffmpeg.probe() can't determine a file's duration
    VideoFileClip = None


def clear_fluid_cache():
    """
    Clear the in-process fluid file cache deduplication set

    Must be called before starting a fresh catalog rebuild in a long-running
    process (e.g. the web server API) so that scan_file_cache runs again for
    each unique content_dir.  In short-lived processes (station_42.py) this
    is a no-op since the set is always empty at process start.
    """
    ShowCatalog._fluid_cache_scanned.clear()


def _get_required_video_duration(path):
    """
    Probe a required video's positive duration in seconds, raising if both probe methods fail
    """

    duration, error_hint = media_processor._get_duration(path)
    if duration > 0.0:
        return duration

    if VideoFileClip is not None:
        try:
            video_clip = VideoFileClip(path)
            duration = video_clip.duration
            video_clip.close()
            if duration and duration > 0.0:
                return duration
        except Exception:
            pass

    hint = ' ({})'.format(error_hint) if error_hint else ''
    raise RuntimeError('Could not determine duration for required video file: {0}{1}'.format(path, hint))


def _harvest_slot(slot, tags, bump_overrides, commercial_overrides, start_bumps, end_bumps):
    """
    Collect a schedule slot's content and break-media references into the supplied indexes

    :param slot:                 (dict) hourly schedule settings to inspect
    :param tags:                 (dict) content tags to mark as required
    :param bump_overrides:       (dict) alternative bump directories to collect
    :param commercial_overrides: (dict) alternative commercial directories to collect
    :param start_bumps:          (dict) explicit opening bump paths to collect
    :param end_bumps:            (dict) explicit closing bump paths to collect
    """
    # collects the tags and directory overrides declared by a single slot
    if 'tags' in slot:
        if type(slot['tags']) is list:
            for tag in slot['tags']:
                tags[tag] = True
        else:
            tags[slot['tags']] = True

    if 'bump_dir' in slot:
        bump_overrides[slot['bump_dir']] = True
    if 'commercial_dir' in slot:
        commercial_overrides[slot['commercial_dir']] = True
    if 'start_bump' in slot:
        start_bumps[slot['start_bump']] = True
    if 'end_bump' in slot:
        end_bumps[slot['end_bump']] = True


class ShowCatalog(object):
    """
    Build a station's media catalog and select programs and break content for scheduling
    """
    prebump = 'prebump'
    postbump = 'postbump'

    # Tracks content_dirs already scanned by FluidBuilder in this process run.
    # Prevents redundant directory walks when multiple stations share the same
    # content_dir (e.g. Comedy 1-4 all under catalog/movies).
    _fluid_cache_scanned = set()

    def __init__(self, config, rebuild_catalog=False, load=True, debug=False, force=False,
                 skip_chapter_scan=False):
        """
        Initialize catalog indexes and optionally load or rebuild the station's media catalog

        :param config:            (dict) processed station configuration
        :param rebuild_catalog:   (bool) whether to scan media and write a rebuilt catalog
        :param load:              (bool) whether to load stored entries when not rebuilding
        :param debug:             (bool) retained constructor option; currently unused
        :param force:             (bool) whether to delete existing entries before rebuilding
        :param skip_chapter_scan: (bool) whether to skip chapter discovery during media scans
        """
        self.config = config
        self._l = logging.getLogger('{} - CAT'.format(self.config['network_name']))

        # the main index for videos
        self.clip_index = {}
        # the tag/duration cache index
        self.tag_dur_cache = {}

        # basically, a flattened list of clip_index keys
        self.tags = []

        self.__fluid_builder = None
        self.min_gap = 3
        self.skip_chapter_scan = skip_chapter_scan
        if rebuild_catalog:
            if force:
                self._l.info('Rebuilding catalog with force flag - will delete existing catalog')
                catalog_api.delete_catalog(self.config)
            self.build_catalog()
        elif load:
            self.load_catalog()

    def _write_catalog(self):
        """
        Flatten the in-memory tag index and replace the station's stored catalog entries
        """
        # first, make them into a flat list
        flat_list = []

        for tag in self.clip_index:
            try:
                for entry in self.clip_index[tag]:
                    if isinstance(entry, CatalogEntry):
                        flat_list.append(entry)
                    else:
                        _logger.warning(
                            'Warning: Entry {0} on {1} is not a CatalogEntry instance. Skipping.'.format(
                                entry, tag))

            except Exception as e:
                _logger.error("Error processing tag '{0}': {1}".format(tag, e))

        catalog_api.set_entries(self.config, flat_list)

    def load_catalog(self):
        """
        Load stored media into a tag index, skipping streaming networks
        """
        if self.config['network_type'] == 'streaming':
            return

        catalog_entries = catalog_api.get_entries(self.config)

        self.clip_index = {}

        for entry in catalog_entries:

            if entry.tag not in self.clip_index:
                self.clip_index[entry.tag] = []
            self.clip_index[entry.tag].append(entry)

    def build_catalog(self):
        """
        Scan and persist media according to the station's network type

        Initialize the shared fluid cache for standard networks, scan a single directory
        for loop networks, and skip streaming networks. Guide catalogs are unsupported.
        """
        self._l.info('Starting catalog build for {}'.format(self.config['network_name']))

        match self.config['network_type']:
            case 'standard':
                if FF_USE_FLUID_FILE_CACHE:
                    from fs42.tools.media.fluid_builder import FluidBuilder

                    self.__fluid_builder = FluidBuilder()
                    media_filter = self.config.get('media_filter', 'video')
                    cache_key = (os.path.realpath(self.config['content_dir']), media_filter)
                    if cache_key not in ShowCatalog._fluid_cache_scanned:
                        self._l.info('Initializing fluid file cache...')
                        self.__fluid_builder.scan_file_cache(self.config['content_dir'], media_filter)
                        ShowCatalog._fluid_cache_scanned.add(cache_key)
                        self._l.info('Fluid file cache updated - continuing build')
                    else:
                        self._l.info('Fluid file cache already scanned for this content_dir - skipping')

                return self._build_standard()
            case 'loop':
                return self._build_single()
            case 'guide':
                raise NotImplementedError('Guide catalog not supported yet.')
            case 'streaming':
                # just return for now
                return

    def _build_single(self, tag='content'):
        """
        Catalog a loop station's media directory under one tag and save the entries

        :param tag: (str) content group assigned to every discovered media file
        """
        self.clip_index = {}
        self.tags = []
        # for station types with all files in a single directory
        media_filter = self.config.get('media_filter', 'video')
        self._l.info('Checking for media in {0} for single directory with filter={1}'.format(
            self.config['content_dir'], media_filter))
        file_list = media_processor._find_media(self.config['content_dir'], media_filter)
        self.clip_index[tag] = media_processor._process_media(file_list, tag, content_type='feature')
        self._l.info('Building complete - processed {} files'.format(len(file_list)))
        self._write_catalog()

    def _build_tags(self):
        """
        Refresh the tag list from the current in-memory catalog index
        """
        self.tags = list(self.clip_index.keys())

    def _build_standard(self):
        """
        Catalog media referenced by regular schedules, overrides, clip shows, and break settings
        """
        self.clip_index = {}
        self.tags = []

        self._l.info('Standard network')
        start_bumps = {}
        end_bumps = {}

        # get the list of all tags
        tags = {}
        bump_overrides = {}
        commercial_overrides = {}
        for day in DAYS:
            slots = self.config[day]
            for k in slots:
                # Validate that slots[k] is a dictionary
                if not isinstance(slots[k], dict):
                    self._l.error('Invalid slot configuration for {0}[{1}]: expected dict, got {2}'.format(
                        day, k,
                        type(slots[k]).__name__))
                    self._l.error('This may be caused by media processing failures. Check logs above for errors.')
                    self._l.error('Slot value: {}'.format(slots[k]))
                    raise TypeError(
                        'Invalid slot configuration for {0}[{1}]: expected dict, got {2}. Check media processing logs for errors.'
                        .format(day, k,
                                type(slots[k]).__name__))

                # note bump/commercial dirs are collected too - slots can have them without tags
                _harvest_slot(slots[k], tags, bump_overrides, commercial_overrides, start_bumps, end_bumps)

        # check for tag overrides
        tag_overrides = self.config.get('tag_overrides', {})
        for override in tag_overrides.values():
            if 'bump_dir' in override:
                bump_overrides[override['bump_dir']] = True
            if 'commercial_dir' in override:
                commercial_overrides[override['commercial_dir']] = True
            if 'start_bump' in override:
                start_bumps[override['start_bump']] = True
            if 'end_bump' in override:
                end_bumps[override['end_bump']] = True

        # check for date override tags
        date_overrides = self.config.get('date_overrides', {})
        for override_slots in date_overrides.values():
            for slot in override_slots.values():
                if not isinstance(slot, dict):
                    continue
                _harvest_slot(slot, tags, bump_overrides, commercial_overrides, start_bumps, end_bumps)

        # check for week override tags
        week_overrides = self.config.get('week_overrides', {})
        for week_schedule in week_overrides.values():
            for day_key in DAYS:
                if day_key not in week_schedule:
                    continue
                for slot in week_schedule[day_key].values():
                    if not isinstance(slot, dict):
                        continue
                    _harvest_slot(slot, tags, bump_overrides, commercial_overrides, start_bumps, end_bumps)

        # check for fallback tag
        if 'fallback_tag' in self.config:
            tags[self.config['fallback_tag']] = True

        # add any clip show not already in it
        for clip_tag in self.config['clip_shows']:
            tags[clip_tag] = True
            # include clip show start and end clips
            if 'start_clip' in self.config['clip_shows'][clip_tag]:
                tags[self.config['clip_shows'][clip_tag]['start_clip']] = True
            if 'end_clip' in self.config['clip_shows'][clip_tag]:
                tags[self.config['clip_shows'][clip_tag]['end_clip']] = True

        self.clip_index['start_bumps'] = []
        self.clip_index['end_bumps'] = []

        # collect start and end bumps first
        for fp in start_bumps:
            self.__bump_collector('start_bumps', fp)

        for fp in end_bumps:
            self.__bump_collector('end_bumps', fp)

        # now inspect the tags and scan corresponding folders for media
        self.tags = list(tags.keys())
        # populate each tag
        total_count = 0
        for tag in self.tags:
            total_count += self._scan_directory(tag)

        # add commercial and bumps to the tags
        if 'commercial_dir' in self.config and self.config['commercial_dir']:
            total_count += self._scan_directory(self.config['commercial_dir'], content_type='commercial')
        # setup the general bump dir
        if 'bump_dir' in self.config and self.config['bump_dir']:
            total_count += self._scan_directory(self.config['bump_dir'], is_bumps=True, content_type='bump')

        for override_dir in bump_overrides:
            total_count += self._scan_directory(override_dir, is_bumps=True, content_type='bump')

        for override_dir in commercial_overrides:
            total_count += self._scan_directory(override_dir, content_type='commercial')

        # scan next/ folder for coming-up-next bumpers
        # folder naming convention (-- is the separator between show tags):
        #   --ShowB                        = next is ShowB (no current show context)
        #   --ShowB--ShowC                 = next ShowB, then ShowC
        #   --ShowB--ShowC--ShowD          = next ShowB, then ShowC, then ShowD
        #   ShowA--ShowB                   = watching ShowA, next ShowB
        #   ShowA--ShowB--ShowC            = watching ShowA, next ShowB, then ShowC
        #   ShowA--ShowB--ShowC--ShowD     = watching ShowA, next ShowB, then ShowC, then ShowD
        next_dir = '{}/next'.format(self.config['content_dir'])
        if os.path.isdir(next_dir):
            media_filter = self.config.get('media_filter', 'video')
            for subfolder in os.listdir(next_dir):
                subfolder_path = '{0}/{1}'.format(next_dir, subfolder)
                if os.path.isdir(subfolder_path):
                    tag_key = 'next/{}'.format(subfolder)
                    if tag_key not in self.clip_index:
                        self.clip_index[tag_key] = []
                    file_list = media_processor._find_media(subfolder_path, media_filter)
                    clips = media_processor._process_media(file_list, tag_key, content_type='bump')
                    subdir_clips = media_processor._process_subs(subfolder_path, tag_key, bumpdir=True,
                                                                 fluid=self.__fluid_builder, content_type='bump',
                                                                 media_filter=media_filter)
                    self.clip_index[tag_key] = clips + subdir_clips
                    total_count += len(self.clip_index[tag_key])
                    self._l.info('Found {0} coming-up-next bumpers in {1}'.format(
                        len(self.clip_index[tag_key]), tag_key))

        # add sign-off and off-air videos to the clip index
        if 'sign_off_video' in self.config:
            self._l.debug('Adding sign-off video')
            duration = _get_required_video_duration(self.config['sign_off_video'])
            self.clip_index['sign_off'] = [
                CatalogEntry(self.config['sign_off_video'], duration, 'sign_off', content_type='sign_off')
            ]
            self._l.debug('Added sign-off video {}'.format(self.config['sign_off_video']))
            total_count += 1

        if 'off_air_video' in self.config:
            self._l.debug('Adding off air video')
            duration = _get_required_video_duration(self.config['off_air_video'])
            self.clip_index['off_air'] = [
                CatalogEntry(self.config['off_air_video'], duration, 'off_air', content_type='off_air')
            ]
            self._l.debug('Added off air video {}'.format(self.config['off_air_video']))
            total_count += 1

        if 'off_air_image' in self.config:
            self._l.debug('Adding offair image')
            self.clip_index['off_air_image'] = CatalogEntry(self.config['off_air_image'], MIN_5, 'off_air',
                                                            content_type='off_air')
            self._l.debug('Added off air image {}'.format(self.config['off_air_image']))
            total_count += 1

        self._l.info('Catalog build complete. Added {} clips to catalog.'.format(total_count))
        self._build_tags()
        self._write_catalog()

        # sequences only include catalogued files, so scan them once the catalog is written
        sequence_api.scan_sequences(self.config)

    def _scan_directory(self, tag, is_bumps=False, content_type='feature'):
        """
        Scan a content tag and its subfolders, preserving hints and optional bump positions

        :param tag:          (str) directory relative to content_dir, or an absolute directory path
        :param is_bumps:     (bool) whether to separate pre-break and post-break bump entries
        :param content_type: (str) playback category to assign to discovered media
        :return:             (int) number of entries added; previously scanned or empty tags add none
        """
        count_added = 0
        if not tag:
            self._l.debug(
                'Skipping _scan_directory call with empty tag - check commercial_dir or clip_shows config')
            return 0
        if tag not in self.clip_index:
            self.clip_index[tag] = []
            media_filter = self.config.get('media_filter', 'video')
            self._l.info('Checking for media with tag={0} in content folder with filter={1}'.format(
                tag, media_filter))

            if tag and os.path.isabs(tag):
                tag_dir = tag
            else:
                tag_dir = '{0}/{1}'.format(self.config['content_dir'], tag)

            file_list = media_processor._find_media(tag_dir, media_filter)

            self.clip_index[tag] = media_processor._process_media(file_list, tag, fluid=self.__fluid_builder,
                                                                  content_type=content_type)
            self._l.info('--Found {0} videos in {1} folder'.format(len(self.clip_index[tag]), tag))
            self._l.debug('---- {0} media listing: {1}'.format(tag, self.clip_index[tag]))

            # Scan for chapters
            if self.__fluid_builder and not self.skip_chapter_scan:
                self.__fluid_builder.scan_chapters_for_entries(self.clip_index[tag])

            subdir_clips = media_processor._process_subs(tag_dir, tag, bumpdir=is_bumps,
                                                         fluid=self.__fluid_builder, content_type=content_type,
                                                         media_filter=media_filter)

            self._l.info('--Found {0} videos in {1} subfolders'.format(len(subdir_clips), tag))
            self._l.debug('---- {0} sub folder media listing: {1}'.format(tag, subdir_clips))

            # Scan for chapters in subdirectory clips
            if self.__fluid_builder and not self.skip_chapter_scan:
                self.__fluid_builder.scan_chapters_for_entries(subdir_clips)

            if is_bumps:
                pre_key = '{0}-{1}'.format(tag, ShowCatalog.prebump)
                post_key = '{0}-{1}'.format(tag, ShowCatalog.postbump)
                (pre, fill, post) = media_processor._by_position(subdir_clips, ShowCatalog.prebump,
                                                                 ShowCatalog.postbump)

                # Update the tag attribute on each entry to match the composite key
                for entry in pre:
                    entry.tag = pre_key
                for entry in post:
                    entry.tag = post_key

                self.clip_index[tag] = self.clip_index[tag] + fill
                self.clip_index[pre_key] = pre
                self.clip_index[post_key] = post

                count_added += len(pre) + len(fill) + len(post)
            else:
                self.clip_index[tag] += subdir_clips
                count_added += len(self.clip_index[tag])
        return count_added

    def get_text_listing(self):
        """
        Format the catalog as a readable media listing, excluding sign-off and off-air entries
        """
        content = "TITLE                | TAG        | Duration  | Hints\n"
        for tag in self.clip_index:
            if tag not in ['sign_off', 'off_air']:
                for item in self.clip_index[tag]:
                    content += '{}\n'.format(str(item))
        return content

    def check_catalog(self):
        """
        Log catalog entries shorter than one second, excluding sign-off and off-air media
        """
        too_short = []
        for tag in self.clip_index:
            if tag not in ['sign_off', 'off_air']:
                for item in self.clip_index[tag]:
                    if hasattr(item, 'duration') and item.duration < 1:
                        too_short.append(item)

        if len(too_short):
            _logger.info('{0}Found {1} videos under 1 second in length:{2}'.format(
                COLORS['FAIL'], len(too_short), COLORS['ENDC']))
            for v in too_short:
                _logger.warning('{0}{1}{2}'.format(COLORS['WARNING'], v, COLORS['ENDC']))
        else:
            _logger.info('{0}All checks passed{1}'.format(COLORS['OKGREEN'], COLORS['ENDC']))

    def get_signoff(self):
        """
        Return the station's first sign-off catalog entry, or None when unconfigured
        """
        all_signoff = catalog_api.get_by_tag(self.config, 'sign_off')
        candidate = None
        if all_signoff and len(all_signoff):
            candidate = all_signoff[0]
        return candidate

    def get_offair(self):
        """
        Return the station's first off-air catalog entry, or None when unconfigured
        """
        all_offair = catalog_api.get_by_tag(self.config, 'off_air')
        candidate = None
        if all_offair and len(all_offair):
            candidate = all_offair[0]
        return candidate

    def __bump_collector(self, tag, fp):
        """
        Catalog an explicit bump file or directory relative to the station content directory

        :param tag: (str) existing bump index to append discovered entries to
        :param fp:  (str) bump file or folder path relative to content_dir
        """
        bump_path = '{0}/{1}'.format(self.config['content_dir'], fp)

        to_process = [bump_path]
        # check if this is a dir
        if os.path.isdir(bump_path):
            to_process = media_processor._find_media(bump_path)

        bumps = media_processor._process_media(to_process, tag, fluid=self.__fluid_builder, content_type='bump')

        if len(bumps):
            for fp in bumps:
                self.clip_index[tag].append(fp)
        else:
            self._l.error('{0} specified but not found: {1}'.format(tag, fp))
            self._l.error('File paths for {} should be relative to the content_dir'.format(tag))

    def get_start_bump(self, fp):
        """
        Choose an opening bump matching the requested file suffix or parent-folder name
        """
        return self.__bump_finder('start_bumps', fp)

    def get_end_bump(self, fp):
        """
        Choose a closing bump matching the requested file suffix or parent-folder name
        """
        return self.__bump_finder('end_bumps', fp)

    def __bump_finder(self, bump_tag, fp):
        """
        Select an explicit bump by path suffix, falling back to a random folder match

        :param bump_tag: (str) bump index to search
        :param fp:       (str) requested filename suffix or parent-folder name
        :return:         (dict) selected path and duration in seconds, or None if unmatched
        """
        candidates = []

        # first, was it directly referenced?
        for bump in self.clip_index[bump_tag]:
            if bump.path.endswith(fp):
                candidates.append(bump)
                break

        if not len(candidates):
            clean_match = fp.removesuffix('/')
            for bump in self.clip_index[bump_tag]:
                parent_path = os.path.basename(os.path.dirname(bump.path))

                if parent_path == clean_match:
                    candidates.append(bump)

        if len(candidates):
            winner = random.choice(candidates)
            return {'path': winner.path, 'duration': winner.duration}
        else:
            return None

    def entry_by_fpath(self, fpath):
        """
        Look up a stored media entry by its exact path within this station
        """
        results = catalog_api.get_by_path(self.config, fpath)
        return results

    def _lowest_count(self, candidates):
        """
        Choose randomly among candidates tied for the lowest recorded selection count
        """
        min_count = sys.maxsize
        lowest_matches = []
        for candidate in candidates:
            if candidate.count < min_count:
                min_count = candidate.count
                lowest_matches = [candidate]
            elif candidate.count == min_count:
                lowest_matches.append(candidate)

        return random.choice(lowest_matches)

    def get_all_by_tag(self, tag):
        """
        Return the in-memory entries for a tag, or None when the tag has no content
        """
        if tag in self.clip_index and len(self.clip_index[tag]):
            return self.clip_index[tag]
        else:
            return None

    def find_candidate(self, tag, seconds, when, exclusion_index=None, proposed_start=None, meta_hints=None):
        """
        Choose eligible tagged media with the lowest selection count and increment its count

        Apply scheduling hints and optional sibling-channel overlap exclusions. The count
        is changed in memory; this method does not persist it to the catalog database.

        :param tag:                      (str) content group to search
        :param seconds:                  (float) exclusive maximum duration in seconds; entries must last at least one second
        :param when:                     (datetime) broadcast time used to evaluate scheduling hints
        :param exclusion_index:          (dict) real paths mapped to occupied start/end windows, or None
        :param proposed_start:           (datetime) proposed playback start for overlap checks, or None
        :param meta_hints:               (list) legacy argument replaced by metadata hints from station settings
        :return:                         (CatalogEntry) selected entry, or None for an absent or empty tag
        :raises MatchingContentNotFound: if a populated tag has no eligible candidate
        """
        if tag in self.clip_index and len(self.clip_index[tag]):
            candidates = self.clip_index[tag]
            matches = []

            # filter candidates based on configuration hints in config file
            meta_hints = self.config.get('meta_hints')
            if meta_hints:
                candidates = hint_agent.filter_candidate_entries(when, candidates, meta_hints)

            for candidate in candidates:
                # restrict content to fit and be valid (zero duration is likely not valid)
                if (seconds > candidate.duration >= 1
                        and media_processor._test_candidate_hints(candidate.hints, when)):
                    # skip if a sibling channel is already playing this file in an
                    # overlapping time window (handles same-start AND mid-play overlap)
                    if (exclusion_index is not None and proposed_start is not None and candidate.realpath
                            and candidate.realpath in exclusion_index):
                        proposed_end = proposed_start + datetime.timedelta(seconds=candidate.duration)
                        if any(proposed_start < w_end and w_start < proposed_end
                               for w_start, w_end in exclusion_index[candidate.realpath]):
                            continue
                    matches.append(candidate)
            #random.shuffle(matches)
            if not len(matches):
                err = 'Could not find candidate video for tag={0} under {1} in len - maybe add some shorter content?'.format(
                    tag, seconds)
                raise (MatchingContentNotFound(err))
            result = self._lowest_count(matches)
            # note, this has been migrated
            result.count += 1
            # CatalogAPI.set_play_count(self.config, result.path, result.count)
            return result

    def _augment_candidates(self, candidates, key, seconds, when):
        """
        Append duration- and hint-compatible next-up bumps to the existing candidate list

        :param candidates: (list) mutable pool receiving matching entries
        :param key:        (str) additional catalog tag to inspect
        :param seconds:    (float) exclusive maximum duration in seconds
        :param when:       (datetime) broadcast time used to evaluate hints
        :return:           (list) the updated candidate pool
        """
        if key in self.clip_index:
            extras = [
                c for c in self.clip_index[key] if c.duration < seconds and c.duration >= 1
                and media_processor._test_candidate_hints(c.hints, when)
            ]
            candidates += extras
        return candidates

    def find_bump(self, seconds, when, position=None, bump_tag=None, lookahead=None):
        """
        Choose a least-used eligible bump, including announcements matching upcoming tags

        :param seconds:                  (float) exclusive maximum bump duration in seconds
        :param when:                     (datetime) broadcast time used for scheduling hints
        :param position:                 (str) optional pre-break or post-break position
        :param bump_tag:                 (str) bump directory override, or None to use station settings
        :param lookahead:                (list) current tag followed by up to three upcoming tags, or None
        :return:                         (CatalogEntry) selected bump without incrementing its count
        :raises NoFillerContentFound:    if the selected bump directory has no catalog index
        :raises MatchingContentNotFound: if no candidate satisfies duration and hint constraints
        """
        if not bump_tag:
            bump_tag = self.config['bump_dir']

        if position:
            pre_key = '{0}-{1}'.format(bump_tag, ShowCatalog.prebump)
            post_key = '{0}-{1}'.format(bump_tag, ShowCatalog.postbump)
            if position == ShowCatalog.prebump and pre_key in self.clip_index and len(self.clip_index[pre_key]):
                base_tag = pre_key
            elif position == ShowCatalog.postbump and post_key in self.clip_index and len(
                    self.clip_index[post_key]):
                base_tag = post_key
            else:
                # then none were specified, so use regular bumps
                base_tag = bump_tag
        else:
            base_tag = bump_tag

        if base_tag not in self.clip_index:
            raise NoFillerContentFound("Can't find bump folder for tag={}".format(base_tag))

        # build candidate pool from normal bumps
        candidates = [
            c for c in self.clip_index[base_tag]
            if c.duration < seconds and c.duration >= 1 and media_processor._test_candidate_hints(c.hints, when)
        ]

        # now, filter candidates down
        meta_hints = self.config.get('meta_hints')
        if meta_hints:
            candidates = hint_agent.filter_candidate_entries(when, candidates, meta_hints)

        # augment pool with any matching coming-up-next bumpers from the next/ folder.
        # all matching folders are merged into the pool - they are not prioritized,
        # just additional candidates alongside normal bumps.
        if lookahead:
            current_tag = lookahead[0] if len(lookahead) > 0 else None
            next_tag = lookahead[1] if len(lookahead) > 1 else None
            next_next_tag = lookahead[2] if len(lookahead) > 2 else None
            next_next_next_tag = lookahead[3] if len(lookahead) > 3 else None

            if next_tag:
                # next-only keys (no current show context)
                candidates = self._augment_candidates(candidates, 'next/--{}'.format(next_tag), seconds, when)
                if next_next_tag:
                    candidates = self._augment_candidates(candidates,
                                                          'next/--{0}--{1}'.format(next_tag,
                                                                                   next_next_tag), seconds, when)
                    if next_next_next_tag:
                        candidates = self._augment_candidates(
                            candidates, 'next/--{0}--{1}--{2}'.format(next_tag, next_next_tag, next_next_next_tag),
                            seconds, when)
                # keys with current show context
                if current_tag:
                    candidates = self._augment_candidates(candidates,
                                                          'next/{0}--{1}'.format(current_tag,
                                                                                 next_tag), seconds, when)
                    if next_next_tag:
                        candidates = self._augment_candidates(
                            candidates, 'next/{0}--{1}--{2}'.format(current_tag, next_tag, next_next_tag), seconds,
                            when)
                        if next_next_next_tag:
                            candidates = self._augment_candidates(
                                candidates, 'next/{0}--{1}--{2}--{3}'.format(current_tag, next_tag, next_next_tag,
                                                                             next_next_next_tag), seconds, when)

        if not candidates:
            raise MatchingContentNotFound(
                'Could not find candidate video for tag={0} under {1} in len - maybe add some shorter content?'.
                format(base_tag, seconds))

        return self._lowest_count(candidates)

    def find_commercial(self, seconds, when, commercial_dir):
        """
        Choose a commercial that fits the available seconds and broadcast-time hints
        """
        com_tag = commercial_dir if commercial_dir else self.config['commercial_dir']

        if not len(self.clip_index[com_tag]):
            raise NoFillerContentFound("Can't find filler content in {} - please add commercials.".format(com_tag))
        return self.find_candidate(com_tag, seconds, when)

    # makes blocks of reels in bump-commercial-commercial-bump format
    def make_reel_block(self, when, bumpers=True, target_duration=120, commercial_dir=None, bump_dir=None,
                        lookahead=None):
        """
        Assemble a break from optional bumpers and commercials or commercial-free filler

        The target is approximate; individual selections can make the block longer.
        An enabled autobump may fill the entire break instead.

        :param when:            (datetime) broadcast time for content selection
        :param bumpers:         (bool) whether to include opening and closing bumpers
        :param target_duration: (float) desired break length in seconds
        :param commercial_dir:  (str) commercial tag override, or None for station defaults
        :param bump_dir:        (str) bumper tag override, or None for station defaults
        :param lookahead:       (list) current and upcoming program tags for announcement selection
        :return:                (ReelBlock) selected opening bumper, filler entries, and closing bumper
        """
        reels = []
        remaining = target_duration
        start_candidate = None
        end_candidate = None

        # first, is it a filler reel?
        if autobump_agent.do_fill(self.config):
            fill = autobump_agent.fill_block(self.config, target_duration)
            return ReelBlock(fill, [], None)

        # INSERT AUTO BUMPER LOGIC HERE
        if bumpers:
            if 'autobump' not in self.config:
                start_candidate = self.find_bump(target_duration, when, ShowCatalog.prebump, bump_tag=bump_dir,
                                                 lookahead=lookahead)
                end_candidate = self.find_bump(target_duration, when, ShowCatalog.postbump, bump_tag=bump_dir,
                                               lookahead=lookahead)
            else:
                # then what kind of autobumps?
                autoconf = self.config['autobump']
                strategy = 'both'
                if 'strategy' in autoconf:
                    strategy = autoconf['strategy']

                autos = autobump_agent.gen_bumps(self.config)

                start_candidate = autos.get('message_bump', None)
                end_candidate = autos.get('next_bump', None)

                if strategy == 'start':
                    end_candidate = self.find_bump(target_duration, when, ShowCatalog.prebump, bump_tag=bump_dir,
                                                   lookahead=lookahead)
                elif strategy == 'end':
                    start_candidate = self.find_bump(target_duration, when, ShowCatalog.prebump, bump_tag=bump_dir,
                                                     lookahead=lookahead)

            remaining -= start_candidate.duration
            remaining -= end_candidate.duration

        # aim for lower and should average close over time since the returned can be larger
        while remaining > (target_duration * 0.1):
            if not self.config['commercial_free']:
                candidate = self.find_commercial(target_duration, when, commercial_dir)
            else:
                candidate = self.find_bump(target_duration, when, None, bump_dir, lookahead=lookahead)
            remaining -= candidate.duration
            reels.append(candidate)

        return ReelBlock(start_candidate, reels, end_candidate)

    def make_reel_fill(self, when, length, use_bumpers=True, commercial_dir=None, bump_dir=None, strict_count=None,
                       lookahead=None):
        """
        Build break blocks and fill the remaining gap with short media or standby content

        :param when:           (datetime) broadcast time for content selection
        :param length:         (float) total gap to fill in seconds
        :param use_bumpers:    (bool) whether each main break block includes bumpers
        :param commercial_dir: (str) commercial tag override, or None
        :param bump_dir:       (str) bumper tag override, or None
        :param strict_count:   (int) requested main-block count used to divide the gap, or None
        :param lookahead:      (list) current and upcoming program tags for announcement selection
        :return:               (lst<ReelBlock>) main breaks followed by any remaining filler block
        """
        target_break_duration = self.config['break_duration']

        strategy = self.config.get('break_strategy', None)

        break_info = slot_reader.get_break_info(self.config, when)
        strategy = break_info['break_strategy'] if break_info['break_strategy'] else strategy
        blocks = []
        remaining = length
        if strategy == 'end':
            target_break_duration = length
            try:
                block = self.make_reel_block(when, use_bumpers, target_break_duration,
                                             commercial_dir=commercial_dir, bump_dir=bump_dir, lookahead=lookahead)
                remaining -= block.duration
                blocks.append(block)
            except MatchingContentNotFound:
                self._l.debug(
                    'Could not find matching content for {} seconds - will attempt to fill with BRB'.format(
                        remaining))
        else:
            if strict_count:
                target_break_duration = length / strict_count

            keep_going = True
            while remaining and keep_going:
                block = None
                try:
                    block = self.make_reel_block(when, use_bumpers, target_break_duration,
                                                 commercial_dir=commercial_dir, bump_dir=bump_dir,
                                                 lookahead=lookahead)
                except MatchingContentNotFound:
                    self._l.debug(
                        'Could not find matching content for {} seconds - will attempt to fill with BRB'.format(
                            remaining))

                if block and (remaining - block.duration) > 0:
                    remaining -= block.duration
                    blocks.append(block)

                    if strict_count and len(blocks) >= strict_count:
                        keep_going = False

                else:
                    keep_going = False

        # discard that block and fill using the tightest technique possible
        additional_reels = []

        if autobump_agent.do_fill(self.config):
            fill = autobump_agent.fill_block(self.config, remaining)
            blocks.append(ReelBlock(fill, [], None))
        else:
            keep_going = True
            while remaining and keep_going:
                candidate = None
                try:
                    if not self.config['commercial_free']:
                        candidate = self.find_commercial(seconds=remaining, when=when,
                                                         commercial_dir=commercial_dir)
                    else:
                        candidate = self.find_bump(remaining, when, 'fill', bump_tag=bump_dir)
                except MatchingContentNotFound:
                    if remaining > self.min_gap:
                        self._l.debug(
                            'Could not find matching content for {} seconds - will attempt to fill with BRB'.
                            format(remaining))

                if candidate:
                    additional_reels.append(candidate)
                    remaining -= candidate.duration
                else:
                    # If BRB is enabled, we'll use that to fill the remaining gap
                    if remaining > self.min_gap and 'be_right_back_media' in self.config:
                        brb = CatalogEntry(self.config['be_right_back_media'], duration=remaining, tag='brb')
                        additional_reels.append(brb)
                    keep_going = False
                    remaining = 0

            blocks.append(ReelBlock(None, additional_reels, None))

        return blocks

    def gather_clip_content(self, tag, duration, when, start_clip, end_clip, break_duration=None,
                            break_strategy=None):
        """
        Choose a sequence of clips while reserving part of the slot for breaks

        :param tag:            (str) primary clip-show content tag
        :param duration:       (float) total slot duration in seconds
        :param when:           (datetime) broadcast time for hint checks
        :param start_clip:     (str) optional opening-clip tag
        :param end_clip:       (str) optional closing-clip tag
        :param break_duration: (float) reserved end-break duration in seconds, or None
        :param break_strategy: (str) break placement mode, including end for a final break
        :return:               (list) selected catalog entries in playback order
        """
        current_duration = 0
        keep_going = True
        clips = []

        # industry standard content ratios for television shows
        # 40 minutes per hour (0.67) to 48 minutes per hour (0.80)
        CONTENT_RATIO_MIN = 0.67
        CONTENT_RATIO_MAX = 0.80

        # calculate target content duration range
        # for "end" strategy, break_duration is the total commercial time, so use it directly
        if break_strategy == 'end' and break_duration is not None and break_duration > 0 and break_duration < duration:
            target_content_max = duration - break_duration
            target_content_min = target_content_max * CONTENT_RATIO_MIN / CONTENT_RATIO_MAX
        else:
            target_content_min = duration * CONTENT_RATIO_MIN
            target_content_max = duration * CONTENT_RATIO_MAX

        if start_clip is not None:
            try:
                candidate = self.find_candidate(start_clip, duration, when)
                if not candidate:
                    _logger.warning('Unable to find suitable start_clip candidate for clip show {}.'.format(tag))
                    _logger.info('{} {} {} {}'.format(start_clip, duration, duration - current_duration, when))
                    raise MatchingContentNotFound()
                current_duration += candidate.duration
                clips.append(candidate)
            except MatchingContentNotFound as e:
                # No suitable start clip even though one was requested
                raise e

        final_clip = None
        final_clip_duration = 0
        if end_clip is not None:
            try:
                final_clip = self.find_candidate(end_clip, duration, when)
                if not final_clip:
                    raise MatchingContentNotFound()
                final_clip_duration = final_clip.duration
                current_duration += final_clip_duration
            except MatchingContentNotFound as e:
                # No suitable end clip even though one was requested
                raise e

        while keep_going:
            try:
                # if it is a small or negative number, this will throw an exception when a candidate isn't found
                candidate = self.find_candidate(tag, duration - current_duration, when)
                if not candidate:
                    if len(clips) == 0:
                        raise MatchingContentNotFound(
                            "No content found for tag '{0}' with duration {1:.1f}s".format(
                                tag, duration - current_duration))
                    keep_going = False
                    break

                # check if adding this clip would exceed our maximum content ratio
                projected_duration = current_duration + candidate.duration

                # always add at least one clip, even if it exceeds maximum
                # this prevents returning empty clip lists
                if len(clips) == 0:
                    # first clip - always add it regardless of ratio
                    current_duration += candidate.duration
                    clips.append(candidate)
                elif projected_duration > target_content_max:
                    # for "end" strategy, add the clip if it lands closer to the target than stopping here
                    if break_strategy == 'end' and abs(projected_duration -
                                                       target_content_max) < abs(current_duration -
                                                                                 target_content_max):
                        current_duration += candidate.duration
                        clips.append(candidate)
                    keep_going = False
                elif current_duration >= target_content_min:
                    # we're at or above minimum and under maximum - add the clip
                    current_duration += candidate.duration
                    clips.append(candidate)
                else:
                    # we're still below minimum and won't exceed maximum - add the clip
                    current_duration += candidate.duration
                    clips.append(candidate)

            except MatchingContentNotFound as e:
                if len(clips) == 0:
                    # then there isn't any valid content at all.
                    raise e
                # then there are no more clips, so exit the loop
                keep_going = False

        if final_clip is not None:
            clips.append(final_clip)
        return clips

    def summary(self):
        """
        Format the indexed media and tag counts as a short catalog summary
        """
        (tags, count) = self.summary_data()
        text = '{0} videos under {1} tags'.format(count, tags)
        return text

    def summary_data(self):
        """
        Count indexed tags and their media entries, returning the tag count first
        """
        count = 0
        for tag in self.tags:
            if type(self.clip_index[tag]) is list:
                count += len(self.clip_index[tag])
            else:
                count += 1
        return (len(self.tags), count)
