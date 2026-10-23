#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define playback outcome codes, runtime file locations, display limits, and guide-preview layouts and
compositor keys.
"""
import re

STATE_SHELVE = 'runtime/player_state.bin'

SOCKET_PATH = 'runtime/channel.socket'

STATUS_SOCKET_PATH = 'runtime/play_status.socket'

CRT_DISPLAY_IDENTIFIER = 'HJW MACROSILICON 0x0002E9BD'

CRT_RESOLUTION = (640, 480)

MAX_NORMAL_RESOLUTION = (1920, 1080)

MAX_PLAYBACK_REFRESH = 60.1

_MODE_RE = re.compile(r'^(?P<width>\d+)x(?P<height>\d+) px,\s+'
                      r'(?P<refresh>[0-9.]+) Hz(?:\s+\((?P<flags>[^)]*)\))?$')

CRT_PREVIEW = {
    'x': 375,
    'y': 0,
    'width': 265,
    'height': 194,
}

NORMAL_PREVIEW = {
    'x': 1125,
    'y': 0,
    'width': 795,
    'height': 436,
}

# The compositor needs fixed MoveTo coordinates. Pick the closest common
# display aspect, while the guide overlay paints the exact black letterbox bars.
ASPECT_PROFILES = (
    ('4_3', 4.0 / 3.0),
    ('16_9', 16.0 / 9.0),
    ('1_85', 1.85),
    ('2_0', 2.0),
    ('2_39', 2.39),
)

PREVIEW_KEYS = {
    ('crt', '4_3'): 'F10',
    ('crt', '16_9'): 'F11',
    ('crt', '1_85'): 'F12',
    ('crt', '2_0'): 'F13',
    ('crt', '2_39'): 'F14',
    ('normal', '4_3'): 'F15',
    ('normal', '16_9'): 'F16',
    ('normal', '1_85'): 'F17',
    ('normal', '2_0'): 'F18',
    ('normal', '2_39'): 'F19',
}


class PlayerState(object):
    """
    Name the outcomes and control transitions exchanged by player components
    """
    FAILED = 1
    EXITED = 2
    SUCCESS = 3
    CHANNEL_CHANGE = 4
    EXIT_COMMAND = 5
    PLAY_FILE = 6
    PARENTAL_CONTROLS = 7
    ON_DEMAND = 8
