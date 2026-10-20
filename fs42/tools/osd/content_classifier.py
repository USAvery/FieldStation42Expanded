#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage content classifier
"""
import os
import json


class ContentType(object):
    """
    Content type constants matching the values in play_status.socket
    """
    FEATURE = 'feature'
    COMMERCIAL = 'commercial'
    BUMP = 'bump'
    SIGN_OFF = 'sign_off'
    OFF_AIR = 'off_air'
    GUIDE = 'guide'
    WEB = 'web'
    MUSIC = 'music'
    UNKNOWN = 'unknown'


class ContentClassifier(object):
    """
    Reads content type directly from play_status.socket

    The content type is now explicitly tagged during catalog building and
    written to the status socket by the player, eliminating the need to
    infer content type from file paths.
    """

    def __init__(self, socket_file='runtime/play_status.socket'):
        """
        Initialize the instance
        """
        self.socket_file = os.fspath(socket_file)

    def _read_socket_status(self):
        """
        Read and parse the status socket JSON
        """
        try:
            with open(self.socket_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    return None
                return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            return None

    def classify_from_socket(self):
        """
        Read content type from the status socket

        :return: The content_type value from the socket, or ContentType.UNKNOWN if not available.
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
        Deprecated: Classification is now explicit in the status socket
        This method is kept for backward compatibility but simply reads from the socket.
        """
        return self.classify_from_socket()


def classify_current_content(socket_file='runtime/play_status.socket'):
    """
    Classify current content
    """
    classifier = ContentClassifier(socket_file)
    return classifier.classify_from_socket()
