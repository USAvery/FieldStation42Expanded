#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage constants
"""
USE_FLUID_FILE_CACHE = True
LOG_FORMAT = '%(asctime)s:%(levelname)s:%(name)s:%(message)s'
SERVER_MESSAGE = ('FS42 web server is running on this machine. '
                  'Open http://localhost:4242 to manage catalogs and schedules.')
CACHE_TABLES = {'chapters': 'chapter_points', 'breaks': 'break_points'}
