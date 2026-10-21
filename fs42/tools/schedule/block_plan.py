#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Represent one playback-plan segment with its media path, offset, duration, stream flag, and content
and media types.
"""


class BlockPlanEntry(object):
    """
    Describe one timed media segment for the player to seek to and play
    """

    def __init__(self, the_path, skip=0, duration=-1, is_stream=False, content_type='feature', media_type='video'):
        """
        Store a media segment's path, seek offset, duration, and playback categories

        :param the_path:     (str) media path or stream URL
        :param skip:         (float) offset into the source media in seconds
        :param duration:     (float) playback limit in seconds; -1 leaves the duration unspecified
        :param is_stream:    (bool) whether the source should be treated as a stream
        :param content_type: (str) category such as feature, bump, or commercial
        :param media_type:   (str) media format category such as video or audio
        """
        self.path = the_path
        self.skip = skip
        self.duration = duration
        self.is_stream = is_stream
        self.content_type = content_type
        self.media_type = media_type

    def to_json(self):
        """
        Serialize the segment's path, timing, stream flag, and media categories
        """
        return {
            'path': self.path,
            'skip': self.skip,
            'duration': self.duration,
            'is_stream': self.is_stream,
            'content_type': self.content_type,
            'media_type': self.media_type
        }

    def __str__(self):
        """
        Format the segment path, seek offset, and duration for playback diagnostics
        """
        return 'PlanEntry: {0} skip={1} duration={2}'.format(self.path, self.skip, self.duration)
