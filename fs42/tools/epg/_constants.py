#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage constants
"""

DEFAULT_DB_PATH = 'runtime/epg.sqlite'

DEFAULT_SOURCES = {
    'epgshare_us2': {
        'url': 'https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz',
    },
}

DEFAULT_USER_AGENT = 'FieldStation42-EPG/1.0'

DEFAULT_PAST_HOURS = 24

DEFAULT_FUTURE_DAYS = 10

BATCH_SIZE = 500
