#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read audio display metadata and convert configured RGBA values to Qt drawing colors
"""
import os

from PySide6.QtGui import QColor

from fs42.tools.media import metadata_io


class OverlayError(Exception):
    pass


def read_metadata(file_path, db_path):
    """
    Read cached audio fields or use the media filename when no metadata is stored

    :param file_path: (str) playing media path used for cache lookup
    :param db_path:   (str) metadata database filename
    :return:          (dict) title, artist, album, year, and genre fields for display
    """
    metadata = metadata_io.read(file_path, db_path)
    if metadata:
        return {'title': metadata.get('title', 'Unknown Track'),
                'artist': metadata.get('artist', ''),
                'album': metadata.get('album', ''),
                'year': metadata.get('year', ''),
                'genre': metadata.get('genre', '')}
    return {'title': os.path.splitext(os.path.basename(file_path))[0],
            'artist': '', 'album': '', 'year': '', 'genre': ''}


def create_colors(theme):
    """
    Build an independent Qt color palette from an overlay theme's RGB or RGBA tuples

    :param theme: (dict) color names mapped to channel-value tuples
    :return:      (dict) color names mapped to QColor instances
    """
    return {name: QColor(*channels) for name, channels in theme.items()}
