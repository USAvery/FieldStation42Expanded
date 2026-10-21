#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Represent program, clip, web, off-air, loop, and commercial-reel blocks and expand them into timed
playback plans.
"""
import random
import os.path
import datetime

from fs42.core import timings
from fs42.tools.media import reel_cutter
from fs42.tools.media import media_processor
from fs42.tools.media.fluid_builder import FluidBuilder
from fs42.tools.schedule.block_plan import BlockPlanEntry


def clip_break_points(break_points, max_breaks, content_duration):
    """
    Merge content segments to limit the number of break positions

    :param break_points:     (list) detected black-frame or chapter boundaries
    :param max_breaks:       (int) maximum number of content segments to retain
    :param content_duration: (float) complete feature duration in seconds
    :return:                 (list) chapter_start and chapter_end dictionaries covering the selected segments
    """
    # ensure start ordering
    break_points = media_processor.calc_black_segments(break_points, content_duration)

    # Handle edge cases
    if max_breaks <= 0 or len(break_points) == 0:
        return []

    if len(break_points) <= max_breaks:
        return break_points

    # Merge adjacent chapters to create evenly-distributed segments
    # This ensures no content is skipped, just fewer commercial breaks
    max_breaks = int(max_breaks)

    # Calculate which chapter boundaries to keep as break insertion points
    # For max_breaks segments, we need (max_breaks - 1) commercial breaks
    num_breaks = max_breaks - 1

    # Select evenly-distributed break positions
    step = (len(break_points) - 1) / num_breaks if num_breaks > 0 else 0
    break_indices = []
    for i in range(1, max_breaks):  # Start from 1, not 0 (skip the first chapter start)
        index = round(i * step)
        if index not in break_indices and index < len(break_points):
            break_indices.append(index)

    # Create merged segments by combining chapters between selected break points
    merged_segments = []
    segment_start_idx = 0

    for break_idx in break_indices:
        # Merge all chapters from segment_start_idx to break_idx into one segment
        merged_segment = {
            'chapter_start': break_points[segment_start_idx]['chapter_start'],
            'chapter_end': break_points[break_idx]['chapter_start'],
        }
        merged_segments.append(merged_segment)
        segment_start_idx = break_idx

    # Add the final segment (from last break to end)
    final_segment = {
        'chapter_start': break_points[segment_start_idx]['chapter_start'],
        'chapter_end': break_points[-1]['chapter_end'],
    }
    merged_segments.append(final_segment)

    return merged_segments


class LiquidBlock(object):
    """
    Represent a scheduled program and construct its feature-and-break playback plan
    """

    def __init__(self, content, start_time, end_time, title=None, break_strategy='standard', break_info=None):
        """
        Store scheduled content, broadcast boundaries, and per-slot break settings

        :param content:        (CatalogEntry) feature media; subclasses may supply a list of clips
        :param start_time:     (datetime) scheduled broadcast start
        :param end_time:       (datetime) scheduled broadcast end
        :param title:          (str) guide title, or None to use the media title
        :param break_strategy: (str) placement rule for inserted breaks
        :param break_info:     (dict) opening and closing bumps and directory overrides, or None
        """
        self.content = content
        # the requested starting time
        self.start_time = start_time
        # the expected/requested end time
        self.end_time = end_time
        if title is None and type(content) is not list:
            self.title = content.title
        else:
            self.title = title
        self.reel_blocks = None
        self.plan = None

        self.break_info = break_info if break_info else {}

        self.sequence_key = None

        if break_info:
            #print("break info: ", break_info)
            self.start_bump = break_info.get('start_bump', None)
            self.end_bump = break_info.get('end_bump', None)
            self.bump_override = break_info.get('bump_dir', None)
            self.commercial_override = break_info.get('commercial_dir', None)

        self.break_strategy = break_strategy

        # set by liquid_schedule before make_plan() is called
        # index 0=current, 1=next, 2=next-next, 3=next-next-next
        self.lookahead = []

    def __str__(self):
        """
        Format the program's broadcast interval, title, and source filename
        """
        content = os.path.basename(self.content.path)
        return '{0} - {1} - {2} - {3}'.format(self.start_time.strftime('%m/%d %H:%M'),
                                              self.end_time.strftime('%H:%M'), self.title, content)

    def content_duration(self):
        """
        Return the feature's original playback length in seconds
        """
        return self.content.duration

    def playback_duration(self):
        """
        Return the scheduled interval's timedelta seconds component
        """
        return (self.end_time - self.start_time).seconds

    def buffer_duration(self):
        """
        Calculate the scheduled seconds remaining after the feature's duration
        """
        return self.playback_duration() - self.content_duration()

    def make_plan(self, catalog):
        """
        Split the feature at chapter or black-frame boundaries and insert break media

        Use catalog selection to fill spare time and store the resulting playback plan
        on this block. Reject a scheduled interval materially shorter than its content.

        :param catalog: (ShowCatalog) station catalog supplying commercials and bumpers
        """
        # first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()

        _fluid = FluidBuilder()

        # Prefer chapter markers over black detection
        break_points = _fluid.get_chapters(self.content.realpath)
        if not break_points:
            # Fall back to black detection if no chapters
            break_points = _fluid.get_breaks(self.content.realpath)

        strict_count = None
        if break_points:
            # Calculate how many breaks we need based on break_duration config
            # If break_duration is configured, use it to determine break count
            break_duration = self.break_info.get('break_duration', None)
            if break_duration is None:
                # Try to get from catalog config if not in break_info
                break_duration = catalog.config.get('break_duration', None)

            if break_duration and break_duration > 0:
                # Calculate desired number of breaks based on total buffer and break_duration
                # This respects the user's break_duration setting
                desired_breaks = max(1, int(diff / break_duration))

                # break_points contains content segments, so we need desired_breaks + 1 segments
                desired_segments = desired_breaks + 1

                # If we have more chapter markers than needed, select the best-positioned ones
                if len(break_points) > desired_segments:
                    break_points = clip_break_points(break_points, desired_segments, self.content_duration())

                # strict_count is the number of reel blocks (commercial breaks) to create
                # This is one less than the number of content segments
                strict_count = len(break_points) - 1 if len(break_points) > 0 else 0
            else:
                # Fallback: limit breaks to no more than every 2 minutes of playback
                max_breaks = self.playback_duration() / timings.MIN_2
                # We need max_breaks + 1 content segments to create max_breaks commercial breaks
                max_segments = int(max_breaks) + 1

                if len(break_points) > max_segments:
                    break_points = clip_break_points(break_points, max_segments, self.content_duration())

                # strict_count is the number of reel blocks (one less than content segments)
                strict_count = len(break_points) - 1 if len(break_points) > 0 else 0

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump['duration']

        if self.end_bump:
            diff -= self.end_bump['duration']

        self.reel_blocks = None
        if diff < -2:
            err = 'Schedule logic error: duration requested {0} is less than content {1}'.format(
                self.playback_duration(), self.content_duration())
            err += ' for show named: {}'.format(self.content.title)
            raise (ValueError(err))

        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time,
                diff,
                commercial_dir=self.commercial_override,
                bump_dir=self.bump_override,
                strict_count=strict_count,
                lookahead=self.lookahead,
            )

        else:
            self.reel_blocks = []

        if strict_count:
            rec = 0
            for reel in self.reel_blocks:
                rec += reel.duration

            if strict_count == len(self.reel_blocks):
                pass
            elif strict_count > len(self.reel_blocks):
                # only clip break_points if we have reel blocks to work with
                # if reel_blocks is empty (e.g., diff <= 2), we don't need chapter-based breaks
                if len(self.reel_blocks) > 0:
                    break_points = clip_break_points(break_points, len(self.reel_blocks), self.content_duration())
                else:
                    # no reel blocks = no buffer time = no breaks needed, clear break_points
                    break_points = []
            else:
                # do nothing for now, they will play at end
                pass

        self.plan = reel_cutter.cut_reels_into_base(
            base_clip=self.content,
            reel_blocks=self.reel_blocks,
            base_offset=0,
            base_duration=self.content_duration(),
            break_strategy=self.break_strategy,
            start_bump=self.start_bump,
            end_bump=self.end_bump,
            break_points=break_points,
        )


class LiquidClipBlock(LiquidBlock):
    """
    Represent a clip compilation with breaks inserted between its constituent clips
    """

    def __init__(self, content, start_time, end_time, title=None, break_strategy='standard', break_info=None):
        """
        Require a list of clips and initialize the scheduled compilation

        :param content:        (lst<CatalogEntry>) clips in playback order
        :param start_time:     (datetime) scheduled start
        :param end_time:       (datetime) scheduled end
        :param title:          (str) compilation title for the guide
        :param break_strategy: (str) placement rule for inserted breaks
        :param break_info:     (dict) per-slot break and bumper overrides, or None
        """
        if type(content) is list:
            super(LiquidClipBlock, self).__init__(content, start_time, end_time, title, break_strategy, break_info)
        else:
            raise (TypeError('LiquidClipBlock required content of type list. Got {} instead'.format(
                type(content))))

    def __str__(self):
        """
        Format the compilation's broadcast interval and guide title
        """
        return '{0} - {1} - {2}'.format(self.start_time.strftime('%m/%d %H:%M'), self.end_time.strftime('%H:%M'),
                                        self.title)

    def content_duration(self):
        """
        Sum the original playback durations of every clip in the compilation
        """
        dur = 0
        for clip in self.content:
            dur += clip.duration
        return dur

    def make_plan(self, catalog):
        """
        Fill the compilation's spare time with breaks and interleave them with its clips

        :param catalog: (ShowCatalog) station catalog supplying commercials and bumpers
        """
        self.plan = []
        # first, collect any reels (commercials and bumps) we might need to buffer to the requested duration
        diff = self.playback_duration() - self.content_duration()

        # is there a start bump?
        if self.start_bump:
            diff -= self.start_bump['duration']

        if self.end_bump:
            diff -= self.end_bump['duration']

        # calculate desired number of breaks based on break_duration
        strict_count = None
        break_duration = self.break_info.get('break_duration', None)
        if break_duration is None:
            break_duration = catalog.config.get('break_duration', None)

        if break_duration and break_duration > 0 and diff > 2:
            # calculate how many breaks we want based on total buffer time and break_duration
            strict_count = max(1, int(diff / break_duration))

        self.reel_blocks = None
        if diff < -2:
            err = 'Schedule logic error: duration requested {0} is less than content {1}'.format(
                self.playback_duration(), self.content_duration())
            err += ' for show named: {}'.format(self.content.title)
            raise (ValueError(err))
        if diff > 2:
            self.reel_blocks = catalog.make_reel_fill(
                self.start_time,
                diff,
                commercial_dir=self.commercial_override,
                bump_dir=self.bump_override,
                strict_count=strict_count,
                lookahead=self.lookahead,
            )
        else:
            self.reel_blocks = []

        self.plan = reel_cutter.cut_reels_into_clips(self.content, self.reel_blocks, self.break_strategy,
                                                     self.start_bump, self.end_bump)


class LiquidWebBlock(LiquidBlock):
    """
    Represent browser-rendered content as a single scheduled playback segment
    """

    def __init__(self, content, start_time, end_time, title=None, break_strategy='standard', break_info=None):
        """
        Initialize a scheduled browser segment using the common program-block settings

        :param content:        (CatalogEntry) browser URL and its configured duration
        :param start_time:     (datetime) scheduled start
        :param end_time:       (datetime) scheduled end
        :param title:          (str) guide title, or None for the entry title
        :param break_strategy: (str) inherited setting; no breaks are inserted by this block
        :param break_info:     (dict) inherited break settings, or None
        """
        super(LiquidWebBlock, self).__init__(content, start_time, end_time, title, break_strategy, break_info)

    def make_plan(self, catalog):
        """
        Store one playback entry for the browser content without inserting breaks
        """
        _c = self.content
        self.plan = [
            BlockPlanEntry(_c.path, 0, _c.duration, content_type=_c.content_type, media_type=_c.media_type)
        ]


class LiquidOffAirBlock(LiquidBlock):
    """
    Fill an off-air interval with an optional sign-off followed by looping standby media
    """

    def __init__(self, content, start_time, end_time, title=None, break_strategy='standard', break_info=None,
                 sign_off=None):
        """
        Initialize an off-air interval and its optional opening sign-off

        :param content:        (CatalogEntry) standby media to repeat
        :param start_time:     (datetime) off-air interval start
        :param end_time:       (datetime) time normal programming resumes
        :param title:          (str) guide title, or None for the entry title
        :param break_strategy: (str) inherited break placement setting
        :param break_info:     (dict) inherited break settings, or None
        :param sign_off:       (CatalogEntry) optional media to play once before the standby loop
        """
        super(LiquidOffAirBlock, self).__init__(content, start_time, end_time, title, break_strategy, break_info)
        self.sign_off = sign_off

    def make_plan(self, catalog):
        """
        Repeat off-air media after the sign-off and trim the final segment to the scheduled end
        """
        self.plan = []
        current_mark = self.start_time
        first_loop = True
        while current_mark < self.end_time:
            # only show sign_off on first loop
            if self.sign_off and first_loop:
                _content = self.sign_off
            else:
                _content = self.content
            first_loop = False
            duration = float(_content.duration)
            current_mark += datetime.timedelta(seconds=duration)
            datetime.timedelta()
            if current_mark > self.end_time:
                # then we will clip it to end at end time
                delta = current_mark - self.end_time
                duration -= delta.total_seconds()

            self.plan.append(
                BlockPlanEntry(_content.path, 0, duration, content_type=_content.content_type,
                               media_type=_content.media_type))


class LiquidLoopBlock(LiquidBlock):
    """
    Fill a scheduled interval by cycling through a collection of media entries
    """

    def __init__(self, content, start_time, end_time, title=None, break_strategy='standard', break_info=None,
                 shuffle=False):
        """
        Initialize looping content and its repeat-cycle shuffle option

        :param content:        (lst<CatalogEntry>) media collection to cycle through
        :param start_time:     (datetime) loop interval start
        :param end_time:       (datetime) loop interval end
        :param title:          (str) guide title for the looping interval
        :param break_strategy: (str) inherited break placement setting
        :param break_info:     (dict) inherited break settings, or None
        :param shuffle:        (bool) whether to reshuffle after each complete cycle
        """
        super(LiquidLoopBlock, self).__init__(content, start_time, end_time, title, break_strategy, break_info)
        self.shuffle = shuffle

    def __str__(self):
        """
        Format the loop interval and guide title for a schedule listing
        """
        return '{0} - {1} - {2} - LOOP'.format(self.start_time.strftime('%m/%d %H:%M'),
                                               self.end_time.strftime('%H:%M'), self.title)

    def make_plan(self, catalog):
        """
        Shuffle the initial media order and repeat clips until the interval is filled

        Optionally reshuffle each subsequent cycle and trim the last segment to the
        scheduled end. Store the resulting entries on this block.
        """
        if not self.content:
            raise ValueError('LiquidLoopBlock requires content')
        entries = []
        keep_going = True
        current_mark = self.start_time
        next_mark = None
        current_index = 0
        random.shuffle(self.content)
        while keep_going:
            clip = self.content[current_index]
            next_mark = current_mark + datetime.timedelta(seconds=clip.duration)
            duration = clip.duration
            if next_mark < self.end_time:
                current_index += 1
                if current_index >= len(self.content):
                    current_index = 0
                    if self.shuffle:
                        random.shuffle(self.content)

            else:
                keep_going = False
                duration = (self.end_time - current_mark).total_seconds()

            entries.append(
                BlockPlanEntry(clip.path, 0, duration, content_type=clip.content_type, media_type=clip.media_type))

            current_mark = next_mark
        self.plan = entries


class ReelBlock(object):
    """
    Group an opening bumper, filler media, and closing bumper into one break
    """

    def __init__(self, start_bump=None, comms=[], end_bump=None):
        """
        Store the media components of a commercial break

        :param start_bump: (CatalogEntry) optional opening bumper
        :param comms:      (lst<CatalogEntry>) commercials or other filler in playback order
        :param end_bump:   (CatalogEntry) optional closing bumper
        """
        self.start_bump = start_bump
        self.comms = comms
        self.end_bump = end_bump

    def __str__(self):
        """
        Format the break's total duration and filler-entry count
        """
        return 'ReelBlock: {0} {1}'.format(self.duration, len(self.comms))

    @property
    def duration(self):
        """
        Sum the bumpers and filler durations in seconds
        """
        dur = 0
        if self.start_bump is not None:
            dur += self.start_bump.duration
        for comm in self.comms:
            dur += comm.duration
        if self.end_bump is not None:
            dur += self.end_bump.duration
        return dur

    def make_plan(self):
        """
        Convert break components into ordered playback segments with bump and commercial tags
        """
        entries = []
        if self.start_bump is not None:
            entries.append(
                BlockPlanEntry(self.start_bump.path, 0, self.start_bump.duration, content_type='bump',
                               media_type=self.start_bump.media_type))
        for comm in self.comms:
            entries.append(
                BlockPlanEntry(comm.path, 0, comm.duration, content_type='commercial', media_type=comm.media_type))
        if self.end_bump is not None:
            entries.append(
                BlockPlanEntry(self.end_bump.path, 0, self.end_bump.duration, content_type='bump',
                               media_type=self.end_bump.media_type))
        return entries
