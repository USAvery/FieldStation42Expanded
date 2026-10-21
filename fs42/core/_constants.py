#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define default server, playback, catalog, and scheduling settings used when loading station
configuration.
"""
DEFAULT_SERVER_CONF = {
    'channel_socket': 'runtime/channel.socket',
    'status_socket': 'runtime/play_status.socket',
    'day_parts': {
        'morning': range(6, 10),
        'daytime': range(10, 18),
        'prime': range(18, 23),
        'late': [23, 0, 1, 2],
        'overnight': range(2, 6),
    },
    'time_format': '%H:%M',
    'date_time_format': '%Y-%m-%dT%H:%M:%S',
    'db_path': 'runtime/fs42_fluid.db',
    'start_mpv': True,
    'server_host': '0.0.0.0',
    'server_port': 4242,
    'title_patterns': [],
    'video_seek_timeout': 10,
    'stream_start_timeout': 5,
    'follow_static_symlinks': False,
    'custom_holidays': {},
}
