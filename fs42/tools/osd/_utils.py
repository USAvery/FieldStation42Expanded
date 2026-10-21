#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Register display fonts once and resolve a fallback when a font file cannot be loaded
"""
from PySide6.QtGui import QFont
from PySide6.QtGui import QFontDatabase

from fs42.core import logger as project_logger

from fs42.tools.osd._constants import DEFAULT_FONT


_logger = project_logger.setup('fs42.tools.osd._utils')


_registered_font_families = {}


def resolve_font(font_path, pixel_size):
    """
    Load a font file into Qt and return a font sized in pixels

    Cache the registered family by file path. If loading fails, cache Qt's default
    family instead. The size is in pixels rather than typographic points.

    :param font_path:  (str) font file path, or None to use DEFAULT_FONT
    :param pixel_size: (int) requested font height in pixels
    :return:           (QFont) font configured with the resolved family and pixel size
    """
    path = font_path or DEFAULT_FONT
    family = _registered_font_families.get(path)
    if family is None:
        font_id = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
        if families:
            family = families[0]
        else:
            _logger.warning('[WARNING] Could not load font {}, falling back to default'.format(path))
            family = QFont().defaultFamily()
        _registered_font_families[path] = family

    font = QFont(family)
    font.setPixelSize(pixel_size)
    return font
