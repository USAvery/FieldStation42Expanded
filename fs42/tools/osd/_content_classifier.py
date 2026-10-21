#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read the content-type tag already written by the player to its status file. Return unknown when
status is unavailable so the logo display can distinguish programs from breaks.
"""
import os
import json

from fs42.tools.osd._constants import ContentType


class ContentClassifier(object):
    """
    Read the player's content-type tag so displays can distinguish programs from breaks

    The player writes an explicit tag derived from the catalog; this reader does not
    infer a category from the title, file path, or network name.
    """

    def __init__(self, socket_file='runtime/play_status.socket'):
        """
        Select the player status file to read when requesting a content-type tag

        :param socket_file: (str) filesystem path to the JSON player status file
        """
        self.socket_file = os.fspath(socket_file)

    def _read_socket_status(self):
        """
        Read player status JSON, returning None if the file is empty or cannot be decoded
        """
        try:
            with open(self.socket_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    return None
                status = json.loads(content)
                return status if isinstance(status, dict) else None
        except (OSError, ValueError):
            return None

    def classify_from_socket(self):
        """
        Return the player's content-type tag, using unknown when the tag is unavailable

        :return: (str) stored content_type value, or ContentType.UNKNOWN for missing status or tags
        """
        status_data = self._read_socket_status()
        if not status_data:
            return ContentType.UNKNOWN

        # Read content_type directly from the socket
        content_type = status_data.get('content_type')

        if content_type:
            return content_type

        # If content_type is not present (old data or error), return unknown
        return ContentType.UNKNOWN

    def classify_content(self, title, file_path, network_name):
        """
        Preserve the legacy classification interface by reading the explicit player tag

        :param title:        (str) legacy title argument, ignored
        :param file_path:    (str) legacy media path argument, ignored
        :param network_name: (str) legacy station name argument, ignored
        :return:             (str) current player content-type tag or ContentType.UNKNOWN
        """
        return self.classify_from_socket()


def classify_current_content(socket_file='runtime/play_status.socket'):
    """
    Read the current content-type tag from a player status file

    :param socket_file: (str) filesystem path to the JSON player status file
    :return:            (str) stored content-type tag, or unknown when unavailable
    """
    classifier = ContentClassifier(socket_file)
    return classifier.classify_from_socket()
