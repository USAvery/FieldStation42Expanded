#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define catalog cache switches, terminal report colors, and the location of background videos used by
generated station bumps.
"""
import os

BUMP_VIDEO_DIR = os.path.join('fs42', 'web', 'blueprints', 'menu', 'bump', 'static', 'video')

FF_USE_FLUID_FILE_CACHE = True

FF_USE_CATAGLOG_DB = True

COLORS = {
    'HEADER': '\x1b[95m',
    'OKBLUE': '\x1b[94m',
    'OKCYAN': '\x1b[96m',
    'OKGREEN': '\x1b[92m',
    'WARNING': '\x1b[93m',
    'FAIL': '\x1b[91m',
    'ENDC': '\x1b[0m',
    'BOLD': '\x1b[1m',
    'UNDERLINE': '\x1b[4m'
}
