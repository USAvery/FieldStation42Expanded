#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Assemble playback plans that interleave program segments with commercial reels and station bumps,
using break strategies and optional detected cut points.
"""
from fs42.tools.media import media_processor
from fs42.tools.schedule.block_plan import BlockPlanEntry


def cut_reels_into_base(base_clip, reel_blocks, base_offset, base_duration, break_strategy, start_bump, end_bump,
                        break_points=None):
    """
    Interleave a feature's playable segments with commercial breaks and explicit bumpers

    :param base_clip:      (CatalogEntry) original feature media
    :param reel_blocks:    (list) break blocks to insert
    :param base_offset:    (float) initial seek offset into the feature in seconds
    :param base_duration:  (float) feature duration to play in seconds
    :param break_strategy: (str) placement mode such as standard, center, or end
    :param start_bump:     (dict) optional opening bump path and duration
    :param end_bump:       (dict) optional closing bump path and duration
    :param break_points:   (list) optional chapter or black-frame boundaries
    :return:               (lst<BlockPlanEntry>) complete playback plan in display order
    """
    entries = []
    break_count = 0

    if break_points:
        break_points = media_processor.calc_black_segments(break_points, base_clip.duration)
        #[print(x) for x in break_points]

    if start_bump:
        entries.append(
            BlockPlanEntry(start_bump['path'], 0, start_bump['duration'], content_type='bump',
                           media_type=start_bump.get('media_type', 'video')))

    if reel_blocks:
        break_count = len(reel_blocks)

    if break_count <= 1 or break_strategy == 'end' or break_strategy == 'center':
        if break_strategy == 'center':
            h_dur = base_duration / 2
            h1 = BlockPlanEntry(base_clip.path, base_offset, h_dur, content_type=base_clip.content_type,
                                media_type=base_clip.media_type)
            h2 = BlockPlanEntry(base_clip.path, base_offset + h_dur, h_dur, content_type=base_clip.content_type,
                                media_type=base_clip.media_type)
            entries.append(h1)
        else:
            # then don't cut the base at all
            entries.append(
                BlockPlanEntry(base_clip.path, base_offset, base_duration, content_type=base_clip.content_type,
                               media_type=base_clip.media_type))
        for _block in reel_blocks:
            # and put the reel at the end if there is one
            entries += _block.make_plan()
        if break_strategy == 'center':
            entries.append(h2)
    else:
        # we know break count is greater than 1
        segment_duration = base_clip.duration / break_count
        offset = base_offset

        if not break_points:
            for i in range(break_count):
                entries.append(
                    BlockPlanEntry(base_clip.path, offset, segment_duration, content_type=base_clip.content_type,
                                   media_type=base_clip.media_type))
                entries += reel_blocks[i].make_plan()
                offset += segment_duration
        else:

            keep_going = True

            if len(break_points):
                # Play first segment from start to first break point
                # Use absolute chapter_start position, not cumulative offset
                first_segment = break_points.pop(0)
                segment_duration = first_segment['chapter_end'] - first_segment['chapter_start']
                entries.append(
                    BlockPlanEntry(base_clip.path, first_segment['chapter_start'], segment_duration,
                                   content_type=base_clip.content_type, media_type=base_clip.media_type))

            while keep_going:

                if len(reel_blocks):
                    reel_block = reel_blocks.pop(0)
                    entries += reel_block.make_plan()

                if len(break_points):
                    this_bp = break_points.pop(0)
                    # Play content segment using absolute chapter_start position
                    segment_duration = this_bp['chapter_end'] - this_bp['chapter_start']
                    e = BlockPlanEntry(base_clip.path, this_bp['chapter_start'], segment_duration,
                                       content_type=base_clip.content_type, media_type=base_clip.media_type)
                    entries.append(e)

                if not len(break_points) and not len(reel_blocks):
                    keep_going = False

    if end_bump:
        entries.append(
            BlockPlanEntry(end_bump['path'], 0, end_bump['duration'], content_type='bump',
                           media_type=end_bump.get('media_type', 'video')))

    return entries


def cut_reels_into_clips(clips, reel_blocks, break_stategy, start_bump, end_bump):
    """
    Interleave whole clips with break blocks according to the configured placement strategy

    :param clips:         (lst<CatalogEntry>) compilation clips in playback order
    :param reel_blocks:   (list) commercial breaks to insert
    :param break_stategy: (str) placement mode such as standard, center, or end
    :param start_bump:    (dict) optional opening bump path and duration
    :param end_bump:      (dict) optional closing bump path and duration
    :return:              (lst<BlockPlanEntry>) complete compilation playback plan
    """
    entries = []

    if start_bump:
        entries.append(
            BlockPlanEntry(start_bump['path'], 0, start_bump['duration'], content_type='bump',
                           media_type=start_bump.get('media_type', 'video')))

    if reel_blocks:
        break_count = len(reel_blocks)
    else:
        break_count = 0

    if break_count <= 1 or break_stategy == 'end':
        # then don't cut the base at all
        for clip in clips:
            entries.append(
                BlockPlanEntry(clip.path, 0, clip.duration, content_type=clip.content_type,
                               media_type=clip.media_type))
        for _block in reel_blocks:
            # and put the reel at the end if there is one
            entries += _block.make_plan()
    elif break_stategy == 'center':
        # half clips, then all reels, then second half clips
        half_point = len(clips) // 2

        # First half of clips
        for i in range(half_point):
            clip = clips[i]
            entries.append(
                BlockPlanEntry(clip.path, 0, clip.duration, content_type=clip.content_type,
                               media_type=clip.media_type))

        # All reels
        for _block in reel_blocks:
            entries += _block.make_plan()

        # Second half of clips
        for i in range(half_point, len(clips)):
            clip = clips[i]
            entries.append(
                BlockPlanEntry(clip.path, 0, clip.duration, content_type=clip.content_type,
                               media_type=clip.media_type))
    else:
        # distribute breaks as evenly as possible across clips
        if len(clips) > break_count:
            # more clips than breaks - insert break every N clips
            clips_per_segment = round(len(clips) / break_count)
            for i in range(len(clips)):
                clip = clips[i]
                entries.append(
                    BlockPlanEntry(clip.path, 0, clip.duration, content_type=clip.content_type,
                                   media_type=clip.media_type))
                if len(reel_blocks) and i > 0 and (i % clips_per_segment) == 0:
                    reel_b = reel_blocks.pop(0)
                    entries += reel_b.make_plan()
        else:
            # more breaks than clips - distribute breaks evenly between/after clips
            breaks_per_position = break_count // (len(clips) + 1)  # +1 for position after last clip
            remaining_breaks = break_count % (len(clips) + 1)

            for i in range(len(clips)):
                clip = clips[i]
                entries.append(
                    BlockPlanEntry(clip.path, 0, clip.duration, content_type=clip.content_type,
                                   media_type=clip.media_type))

                # insert breaks after this clip
                breaks_to_insert = breaks_per_position
                if i < remaining_breaks:
                    breaks_to_insert += 1

                for _ in range(breaks_to_insert):
                    if len(reel_blocks):
                        reel_b = reel_blocks.pop(0)
                        entries += reel_b.make_plan()

        # insert any remaining breaks at the end
        while len(reel_blocks):
            reel_b = reel_blocks.pop(0)
            entries += reel_b.make_plan()

    if end_bump:
        entries.append(
            BlockPlanEntry(end_bump['path'], 0, end_bump['duration'], content_type='bump',
                           media_type=end_bump.get('media_type', 'video')))

    return entries
