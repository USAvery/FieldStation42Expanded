#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Register display fonts once and resolve a fallback when a font file cannot be loaded
"""
from dataclasses import fields

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


def create_config(config_type, values):
    """
    Build one display configuration while ignoring fields belonging to another hybrid component

    :param config_type: (type) status, logo, or volume settings class
    :param values:      (dict) decoded JSON display options
    :return:            (obj) normalized display configuration
    """
    names = {setting.name for setting in fields(config_type)}
    return config_type(**{name: value for name, value in values.items() if name in names})


def normalize_config(config):
    """
    Normalize numeric values, booleans, alignments, and colors in lightweight display settings

    :param config: (obj) mutable dataclass containing OSD configuration fields
    """
    from fs42.tools.osd.osd_layout import HAlignment
    from fs42.tools.osd.osd_layout import VAlignment
    for setting in fields(config):
        value = getattr(config, setting.name)
        if setting.name == 'halign':
            value = HAlignment(value)
        elif setting.name == 'valign':
            value = VAlignment(value)
        elif setting.name in ('color', 'text_color'):
            if not isinstance(value, (list, tuple)) or len(value) != 4:
                raise ValueError('{} must contain four color channels'.format(setting.name))
            value = tuple(int(channel) for channel in value)
        elif setting.type is bool:
            if value in (True, 1, 'true', 'True', '1', 'yes', 'on'):
                value = True
            elif value in (False, 0, 'false', 'False', '0', 'no', 'off'):
                value = False
            else:
                raise ValueError('{} must be a boolean'.format(setting.name))
        elif setting.type in (int, float):
            converted = setting.type(value)
            if setting.type is int and isinstance(value, float) and value != converted:
                raise ValueError('{} must be a whole number'.format(setting.name))
            value = converted
        elif setting.type is str or setting.name in ('font', 'default_logo'):
            if not isinstance(value, str) and not (value is None and setting.name in ('font', 'default_logo')):
                raise ValueError('{} must be text'.format(setting.name))
        elif setting.name == 'logo_mapping':
            if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(path, str)
                                                     for key, path in value.items()):
                raise ValueError('logo_mapping must map names to image paths')
        setattr(config, setting.name, value)
