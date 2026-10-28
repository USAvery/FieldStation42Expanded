#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Non-persistent on-screen overlay displays
    now playing
    parental controls
    ticker
"""
from fs42.tools.overlay import _api


# Classes
Overlay = _api.Overlay

# Functions
run_ticker = _api.run_ticker
run_now_playing = _api.run_now_playing
run_parental_controls = _api.run_parental_controls
