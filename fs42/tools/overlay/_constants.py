#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define overlay themes, reference dimensions, animation timing, and default announcement settings
"""
import os

from fs42.core.paths import PROJECT_ROOT


REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
TICKER_INTERVAL_MS = 50
TICKER_SCROLL_STEP_PX = 2
TICKER_WIDTH = 600
TICKER_HEIGHT = 100
TICKER_HEADER_HEIGHT = 32
TICKER_MARGIN = 15
TICKER_BOTTOM_MARGIN = 30
TICKER_LOGO_SPACING = 8
TICKER_LOGO_PATH = os.path.join(PROJECT_ROOT, 'runtime', 'toast_logo.png')
DEFAULT_TICKER_TEXT = 'Welcome to FieldStation42 - Your retro TV experience'
DEFAULT_TICKER_TITLE = 'FS42'
DEFAULT_TICKER_STYLE = 'fieldstation'
DEFAULT_TICKER_ITERATIONS = 2
DEFAULT_PARENTAL_THEME = 'classic'
PARENTAL_BOX_WIDTH = 560
PARENTAL_BOX_HEIGHT = 280
PIN_LENGTH = 4
FONT_FAMILY = 'Arial'
NOW_PLAYING_WIDTH = 500
NOW_PLAYING_HEIGHT = 160
NOW_PLAYING_MARGIN = 80
NOW_PLAYING_PADDING = 20
NOW_PLAYING_TITLE_SIZE = 28
NOW_PLAYING_INFO_SIZE = 20
NOW_PLAYING_LINE_HEIGHT = 40
NOW_PLAYING_FADE_WIDTH = 100
NOW_PLAYING_SHADOW_OFFSET = 2
NOW_PLAYING_COLORS = {
    'background_start': (0, 0, 0, 200),
    'background_end': (20, 20, 20, 180),
    'text': (255, 255, 255),
    'text_shadow': (0, 0, 0, 200),
}

PARENTAL_THEMES = {
    'classic': {
        'box': (12, 20, 38, 235),
        'border': (230, 230, 230),
        'pin_box': (0, 0, 0, 170),
        'text': (255, 230, 80),
        'muted': (220, 205, 120),
        'message': (255, 230, 80),
        'error': (255, 210, 210),
    },
    'modern': {
        'box': (28, 28, 34, 235),
        'border': (90, 170, 255),
        'pin_box': (14, 14, 18, 210),
        'text': (255, 255, 255),
        'muted': (205, 205, 205),
        'message': (225, 225, 225),
        'error': (255, 120, 120),
    },
    'minimal': {
        'box': (245, 245, 245, 235),
        'border': (40, 40, 40),
        'pin_box': (255, 255, 255, 220),
        'text': (20, 20, 20),
        'muted': (80, 80, 80),
        'message': (50, 50, 50),
        'error': (160, 0, 0),
    },
}

TICKER_THEMES = {
    'breaking': {
        'header_start': (220, 0, 0, 240),
        'header_end': (150, 0, 0, 240),
        'background': (8, 8, 16, 200),
        'accent': (255, 255, 255, 80),
        'text_shadow': (0, 0, 0, 150),
    },
    'weather': {
        'header_start': (0, 120, 215, 240),
        'header_end': (0, 80, 160, 240),
        'background': (12, 24, 40, 200),
        'accent': (255, 255, 255, 80),
        'text_shadow': (0, 0, 0, 150),
    },
    'sports': {
        'header_start': (0, 150, 60, 240),
        'header_end': (0, 100, 40, 240),
        'background': (8, 16, 8, 200),
        'accent': (255, 255, 255, 80),
        'text_shadow': (0, 0, 0, 150),
    },
    'financial': {
        'header_start': (255, 140, 0, 240),
        'header_end': (200, 100, 0, 240),
        'background': (20, 12, 8, 200),
        'accent': (255, 255, 255, 80),
        'text_shadow': (0, 0, 0, 150),
    },
    'election': {
        'header_start': (180, 0, 0, 240),
        'header_end': (0, 0, 180, 240),
        'background': (16, 8, 20, 200),
        'accent': (255, 255, 255, 100),
        'text_shadow': (0, 0, 0, 150),
    },
    'fieldstation': {
        'header_start': (40, 80, 140, 240),
        'header_end': (20, 50, 90, 240),
        'background': (8, 12, 20, 200),
        'accent': (120, 180, 255, 100),
        'text_shadow': (0, 0, 0, 150),
    },
}
