#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage constants
"""

# logging.basicConfig(format="%(asctime)s %(levelname)s:%(name)s:%(message)s", level=logging.INFO)

# share of a slot that is not content (commercials and break bumps)
# at least ~2 minutes per 30, ~4 per 60; no more than ~30% commercials
MIN_BREAK_RATIO = 0.067

MAX_BREAK_RATIO = 0.30
