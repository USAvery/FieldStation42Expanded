#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read audio display metadata and convert configured RGBA values to Qt drawing colors
"""
import os


_font_families = {}


class OverlayError(Exception):
    pass


def read_metadata(file_path, db_path):
    """
    Read cached audio fields or use the media filename when no metadata is stored

    :param file_path: (str) playing media path used for cache lookup
    :param db_path:   (str) metadata database filename
    :return:          (dict) title, artist, album, year, and genre fields for display
    """
    from fs42.tools.media import metadata_io
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
    from PySide6.QtGui import QColor
    return {name: QColor(*channels) for name, channels in theme.items()}


def load_font_family(path, default='Arial'):
    """
    Register a custom font once and reuse its family for later metadata presentations

    :param path:    (str) custom font filename, or None for the default family
    :param default: (str) family to use when the font cannot be registered
    :return:        (str) resolved Qt font family
    """
    if not path:
        return default
    if path not in _font_families:
        from PySide6.QtGui import QFontDatabase
        identifier = QFontDatabase.addApplicationFont(path) if os.path.exists(path) else -1
        families = QFontDatabase.applicationFontFamilies(identifier) if identifier >= 0 else []
        _font_families[path] = families[0] if families else default
    return _font_families[path]
