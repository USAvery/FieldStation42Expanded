#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build and scan station sequences, select the next episode or child show, and reset or normalize
saved positions for looping and completion.
"""
import os
import random
import logging

from fs42.core.timings import DAYS
from fs42.tools.catalog import catalog_api
from fs42.tools.media import media_processor
from fs42.tools.sequence._constants import SEASON_RE
from fs42.tools.sequence.sequence import NamedSequence
from fs42.tools.sequence.sequence_io import SequenceIO


def make_sequence_key(station_config, sequence_name, tag_path):
    """
    Build the station, sequence-name, and content-tag identity stored on schedule blocks
    """
    return {'station_name': station_config['network_name'], 'sequence_name': sequence_name, 'tag_path': tag_path}


def get_sequences_for_station(station_config):
    """
    Restore all saved episode sequences belonging to the configured network
    """
    _l = logging.getLogger('SEQUENCE')
    sio = SequenceIO()
    slist = sio.get_all_sequences_for_station(station_config['network_name'])
    return slist


def get_sequence(station_config, sequence_name, tag_path):
    """
    Resolve the active child show and return its saved episode sequence, or None
    """
    _l = logging.getLogger('SEQUENCE')
    sio = SequenceIO()

    tag_path = _get_active_child_sequence(station_config, sequence_name, tag_path)

    seq = sio.get_sequence(station_config['network_name'], sequence_name, tag_path)

    if not seq:
        _l.debug('Sequence {0} for {1} not found.'.format(sequence_name, station_config['network_name']))
        return None

    return seq


def get_next_in_sequence(station_config, sequence_name, tag_path):
    """
    Select the next episode and persist sequence advancement or child-show rotation

    :param station_config: (dict) station settings identifying the network
    :param sequence_name:  (str) configured sequence identifier
    :param tag_path:       (str) content tag or parent show-group path
    :return:               (SequenceEntry) selected episode, or None for missing or empty sequences
    """
    _l = logging.getLogger('SEQUENCE')
    sio = SequenceIO()
    tag_path = _get_active_child_sequence(station_config, sequence_name, tag_path)
    seq = sio.get_sequence(station_config['network_name'], sequence_name, tag_path)

    next_entry = None
    if not seq:
        _l.error('Sequence {0} for {1} not found.'.format(sequence_name, station_config['network_name']))
        return None

    if not _normalize_sequence_position(seq):
        _l.error('Sequence {0}:{1} contains no episodes'.format(sequence_name, tag_path))
        return None

    # Handle end of sequence - reset to 0 to loop back to beginning
    elif seq.current_index >= seq.end_index:
        _l.info('Sequence completed: {0}:{1}'.format(sequence_name, seq.tag_path))
        parent_tag = seq.tag_path.rsplit('/', 1)[0]

        children = sio.get_child_sequences(station_config['network_name'], sequence_name, parent_tag)

        if children:

            next_child = _choose_next_child_sequence(station_config, sequence_name, parent_tag, seq.tag_path)

            _l.info('Switching sequence from {0} -> {1}'.format(seq.tag_path, next_child))

            sio.set_active_sequence(station_config['network_name'], sequence_name, parent_tag, next_child)

            next_seq = sio.get_sequence(station_config['network_name'], sequence_name, next_child)

            next_seq.current_index = next_seq.start_index

            if not _normalize_sequence_position(next_seq):
                _l.error('Child sequence {} contains no episodes'.format(next_child))
                return None

            next_entry = next_seq.episodes[next_seq.current_index]

            next_seq.current_index += 1

            sio.update_current_index(station_config['network_name'], sequence_name, next_child,
                                     next_seq.current_index)

            return next_entry

        _l.debug('Current index {0} reached end of sequence {1}. Looping back to {2}.'.format(
            seq.current_index, sequence_name, seq.start_index))
        seq.current_index = seq.start_index

    try:
        next_entry = seq.episodes[seq.current_index]
    except IndexError:
        _l.error('Error with sequence or tag name')
        _l.error('Sequence {0} for tag {1} failed on current index {2}.'.format(sequence_name, tag_path,
                                                                                seq.current_index))
        _l.error('Try rebuilding sequences with --rebuild_sequences.')
        raise RuntimeError()
    seq.current_index += 1
    sio.update_current_index(station_config['network_name'], sequence_name, tag_path, seq.current_index)

    return next_entry


def reset_by_episode_path(station_config, sequence_name, tag_path, episode_path):
    """
    Move a saved sequence position back to the matching episode path

    :param station_config: (dict) station settings identifying the network
    :param sequence_name:  (str) sequence identifier
    :param tag_path:       (str) content tag identifying the sequence
    :param episode_path:   (str) exact episode filename to resume from
    :return:               (bool) whether the episode was found and the position updated
    """
    _l = logging.getLogger('SEQUENCE')
    sio = SequenceIO()

    # Use the optimized database query instead of loading the entire sequence
    success = sio.update_sequence_index_by_path(station_config['network_name'], sequence_name, tag_path,
                                                episode_path)

    if success:
        _l.info('Reset sequence {0} to episode {1}.'.format(sequence_name, episode_path))
        return True
    else:
        _l.error('Episode path {0} not found in sequence {1}.'.format(episode_path, sequence_name))
        return False


def delete_sequences(station_config):
    """
    Delete the station's saved sequences and their episode entries
    """
    _l = logging.getLogger('SEQUENCE')
    _l.debug('Deleting sequences for {}'.format(station_config['network_name']))
    sio = SequenceIO()
    sio.delete_sequences_for_station(station_config['network_name'])
    _l.debug('Deleted sequences for {}'.format(station_config['network_name']))


def rebuild_sequences(station_config):
    """
    Discard a station's saved sequence positions and rebuild sequences from its slots
    """
    _l = logging.getLogger('SEQUENCE')
    _l.debug('Rebuilding sequences for {}'.format(station_config['network_name']))
    delete_sequences(station_config)
    scan_sequences(station_config)
    _l.debug('Rebuilt sequences for {}'.format(station_config['network_name']))


def scan_sequences(station_config):
    """
    Build or refresh sequences referenced by regular slots and date or week overrides
    """
    for slot in _sequence_slots(station_config):
        _scan_sequence_slot(station_config, slot)


def _sequence_slots(station_config):
    """
    Yield dictionary slots from the regular schedule and date or week overrides
    """
    # first, scan normal weekly schedule slots
    for day in DAYS:
        if day in station_config:
            slots = station_config[day]
            if not isinstance(slots, dict):
                continue

            for slot in slots.values():
                if isinstance(slot, dict):
                    yield slot

    # now scan date_overrides slots, including override-only sequences
    date_overrides = station_config.get('date_overrides', {})
    if isinstance(date_overrides, dict):
        for override_slots in date_overrides.values():
            if not isinstance(override_slots, dict):
                continue

            for slot in override_slots.values():
                if isinstance(slot, dict):
                    yield slot

    # scan week_overrides slots
    week_overrides = station_config.get('week_overrides', {})
    if isinstance(week_overrides, dict):
        for week_schedule in week_overrides.values():
            for day_key in DAYS:
                if day_key not in week_schedule:
                    continue
                slots = week_schedule[day_key]
                if not isinstance(slots, dict):
                    continue
                for slot in slots.values():
                    if isinstance(slot, dict):
                        yield slot


def _scan_sequence_slot(station_config, slot):
    """
    Build sequences for a slot's tags, applying per-show sequence IDs when configured
    """
    if 'sequence' not in slot or 'tags' not in slot:
        return

    # the user supplied sequence name
    if isinstance(slot['tags'], list):
        for tag_index, tag in enumerate(slot['tags']):
            slot_copy = dict(slot)
            if slot.get('sequence_strategy') == 'random_show':
                slot_tag_array = slot.get('sequence_id_array')
                slot_tag_index = ''
                if slot_tag_array is not None:
                    slot_tag_index = '|{}'.format(slot_tag_array[tag_index])

                slot_copy['effective_sequence'] = '{0}{1}'.format(slot['sequence'], slot_tag_index)

                _build_sequence(station_config, tag, slot_copy)
            else:
                _build_sequence(station_config, tag, slot)
    else:
        _build_sequence(station_config, slot['tags'], slot)


def _catalogued_only(catalog_paths, file_list, seq_name, tag):
    """
    Keep sequence files present in the catalog and log omitted media paths

    :param catalog_paths: (set) filenames known to the station catalog
    :param file_list:     (list) discovered episode paths
    :param seq_name:      (str) sequence name for warning messages
    :param tag:           (str) content tag for warning messages
    :return:              (list) paths eligible for sequence storage
    """
    kept = [f for f in file_list if str(f) in catalog_paths]
    skipped = [f for f in file_list if str(f) not in catalog_paths]
    if skipped:
        _l = logging.getLogger('SEQUENCE')
        _l.warning(
            'Sequence {0}:{1}: skipping {2} file(s) not in the catalog (unreadable or zero length?). Run --rebuild_catalog if they should be there.'
            .format(seq_name, tag, len(skipped)))
        for f in skipped:
            _l.warning('  not in catalog: {}'.format(f))
    return kept


def _build_sequence(station_config, this_tag, slot):
    """
    Build or refresh one tag's episode sequence and any random-show child sequences

    :param station_config: (dict) station media directories and catalog settings
    :param this_tag:       (str) content tag to scan
    :param slot:           (dict) sequence name, range, and strategy settings
    """
    _l = logging.getLogger('SEQUENCE')
    seq_tag = this_tag
    seq_name = slot.get('effective_sequence', slot['sequence'])
    real_tag = seq_tag
    sio = SequenceIO()
    if real_tag in station_config['clip_shows']:
        _l.error('Schedule logic error in {}: Clip shows are not currently supported as sequences'.format(
            station_config['network_name']))
        _l.error('{0} is in the clip shows list, but is declared as a sequence on {1} as {2}'.format(
            seq_tag, this_tag, seq_name))
        raise ValueError('Schedule logic error in {}: Clip shows are not currently supported as sequences'.format(
            station_config['network_name']))

    # check if the sequence already exists

    existing = sio.get_sequence(station_config['network_name'], seq_name, seq_tag)

    seq_start = slot.get('sequence_start', 0)
    seq_end = slot.get('sequence_end', 1)
    catalog_paths = set(e.path for e in catalog_api.get_entries(station_config))

    if slot.get('sequence_strategy') == 'random_show':

        seen_child_tags = set()

        base_dir = os.path.join(station_config['content_dir'], real_tag)

        for show_dir in _find_show_dirs(base_dir):

            relative = os.path.relpath(show_dir, base_dir)

            child_tag = '{0}/{1}'.format(seq_tag, relative.replace(os.sep, '/'))

            seen_child_tags.add(child_tag)

            existing_child = sio.get_sequence(station_config['network_name'], seq_name, child_tag)

            file_list = _catalogued_only(catalog_paths, media_processor._rfind_media(show_dir), seq_name,
                                         child_tag)

            if not file_list:
                continue

            if not existing_child:

                ns = NamedSequence(station_config['network_name'], seq_name, child_tag, seq_start, seq_end, 0,
                                   file_list, False)

                sio.put_sequence(station_config['network_name'], ns)

            else:

                disk_files = set(str(f) for f in file_list)
                stored_files = set(entry.fpath for entry in existing_child.episodes)

                if disk_files != stored_files:

                    current_file = None

                    if (existing_child.current_index < len(existing_child.episodes)):
                        current_file = existing_child.episodes[existing_child.current_index].fpath

                    sio.update_sequence_entries(station_config['network_name'], seq_name, child_tag,
                                                list(disk_files), current_file, existing_child.current_index)

        # CLEAN UP STALE SHOWS
        existing_children = set(sio.get_child_sequences(station_config['network_name'], seq_name, seq_tag))

        deleted_children = (existing_children - seen_child_tags)

        for child_tag in deleted_children:

            _l.info('Removing stale child sequence {0}:{1}'.format(seq_name, child_tag))

            sio.delete_sequence(station_config['network_name'], seq_name, child_tag)

        return
    else:
        file_list = _catalogued_only(
            catalog_paths,
            media_processor._rfind_media('{0}/{1}'.format(station_config['content_dir'], real_tag)),
            seq_name,
            seq_tag,
        )
        if not file_list:
            _l.error('Sequence {0}:{1} has no catalogued files - check content and rebuild the catalog.'.format(
                seq_name, seq_tag))

    if not existing:
        seq_start = 0
        seq_end = 1
        if 'sequence_start' in slot:
            seq_start = slot['sequence_start']
        if 'sequence_end' in slot:
            seq_end = slot['sequence_end']

        ns = NamedSequence(station_config['network_name'], seq_name, seq_tag, seq_start, seq_end, 0, file_list,
                           False)
        sio.put_sequence(station_config['network_name'], ns)
    else:
        disk_files = set(str(f) for f in file_list)
        stored_files = set(entry.fpath for entry in existing.episodes)
        if disk_files != stored_files:
            new_on_disk = disk_files - stored_files
            removed_from_disk = stored_files - disk_files
            _l.info('Content changed for sequence {0}: +{1} new, -{2} removed.'.format(
                seq_name, len(new_on_disk), len(removed_from_disk)))
            current_file = None
            if existing.current_index < len(existing.episodes):
                current_file = existing.episodes[existing.current_index].fpath
                _l.debug('Sequence {0}: current_index={1}, current_file={2}'.format(
                    seq_name, existing.current_index, current_file))
            else:
                _l.debug('Sequence {0}: current_index={1} is out of bounds for {2} stored episodes'.format(
                    seq_name, existing.current_index, len(existing.episodes)))
            sio.update_sequence_entries(station_config['network_name'], seq_name, seq_tag, list(disk_files),
                                        current_file, existing.current_index)


def _choose_next_child_sequence(station_config, sequence_name, parent_tag, current_tag_path=None):
    """
    Choose a child show, preferring one that is neither current nor active elsewhere

    :param station_config:   (dict) station settings identifying the network
    :param sequence_name:    (str) show-group sequence identifier
    :param parent_tag:       (str) content directory containing child shows
    :param current_tag_path: (str) child show to avoid repeating, or None
    :return:                 (str) chosen child tag, or None when no children exist
    """
    sio = SequenceIO()

    children = sio.get_child_sequences(station_config['network_name'], sequence_name, parent_tag)

    if not children:
        return None

    active_children = set(sio.get_all_active_sequences(station_config['network_name']))

    available = []

    for child in children:

        if child == current_tag_path:
            continue

        if child in active_children:
            continue

        available.append(child)

    # If every child is already active somewhere, fall back to allowing active children.
    if not available:

        available = [c for c in children if c != current_tag_path]

    # If literally only one child exists, allow it.
    if not available:
        available = children

    return random.choice(available)


def _get_active_child_sequence(station_config, sequence_name, parent_tag):
    """
    Read or choose and persist the active child show, falling back to the original tag
    """
    sio = SequenceIO()

    children = sio.get_child_sequences(station_config['network_name'], sequence_name, parent_tag)

    if not children:
        return parent_tag

    active_child = sio.get_active_sequence(station_config['network_name'], sequence_name, parent_tag)

    if (not active_child or active_child not in children):
        active_child = random.choice(children)

        sio.set_active_sequence(station_config['network_name'], sequence_name, parent_tag, active_child)

    return active_child


def _normalize_sequence_position(seq):
    """
    Repair out-of-range episode positions and report whether the sequence contains media
    """

    if not seq or not seq.episodes:
        return False

    if seq.current_index < -1:
        seq.current_index = -1

    # Pure array-safety guard: only reset when current_index is genuinely
    # past the end of the list. The end-of-sequence case
    # (current_index == len(episodes), which happens when end_perc == 1)
    # must fall through to the completion logic in get_next_in_sequence so
    # that looping / random child-sequence rotation still happens.
    if seq.current_index > len(seq.episodes):
        seq.current_index = 0

    return True


def _find_show_dirs(base_dir):
    """
    Find media-containing show directories and collapse season subfolders to their parent show

    :param base_dir: (str) show-group directory to walk, including symbolic links
    :return:         (lst<str>) sorted unique show directories beneath the group
    """
    show_dirs = []

    for root, dirs, files in os.walk(base_dir, followlinks=True):
        # follow symlinks and skip dotfiles to stay in sync with _rfind_media
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        has_media = any(not f.startswith('.')
                        and f.lower().endswith(tuple('.{}'.format(ext) for ext in media_processor.VIDEO_FORMATS))
                        for f in files)
        if not has_media:
            continue

        rel = os.path.relpath(root, base_dir)

        if rel == '.':
            continue

        parts = rel.split(os.sep)

        # remove trailing season folders
        while parts and SEASON_RE.match(parts[-1]):
            parts.pop()

        if not parts:
            continue

        show_rel = os.path.join(*parts)

        show_dirs.append(os.path.join(base_dir, show_rel))

    return sorted(set(show_dirs))
