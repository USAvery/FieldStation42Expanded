#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define local display-service discovery, command limits, and connection timeouts
"""
import os

from fs42.core.paths import PROJECT_ROOT


STATE_FILE = os.path.join(PROJECT_ROOT, 'runtime', 'display-service.json')
HOST = '127.0.0.1'
START_TIMEOUT = 8.0
REQUEST_TIMEOUT = 2.0
RETRY_INTERVAL = 0.05
MAX_MESSAGE_BYTES = 262144
