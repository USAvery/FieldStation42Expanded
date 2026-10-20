#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage block plan
"""


class BlockPlanEntry(object):
    """
    BlockPlanEntry
    """

    def __init__(self, the_path, skip=0, duration=-1, is_stream=False, content_type='feature', media_type='video'):
        """
        Initialize the instance
        """
        self.path = the_path
        self.skip = skip
        self.duration = duration
        self.is_stream = is_stream
        self.content_type = content_type
        self.media_type = media_type

    def to_json(self):
        """
        ToJSON
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
        Get the display text
        """
        return 'PlanEntry: {0} skip={1} duration={2}'.format(self.path, self.skip, self.duration)
