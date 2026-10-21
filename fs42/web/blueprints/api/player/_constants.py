#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define the volume-status file and adjustment step used by the player-control endpoints.
"""

VOLUME_SOCKET = 'runtime/volume.socket'

# Percentage the volume changes by on each volume up/down request.
VOLUME_STEP = 2
