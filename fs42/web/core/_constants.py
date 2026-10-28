#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define web asset locations, page registrations and legacy mount aliases, and TMDB service and cache
settings.
"""
import os

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(WEB_DIR, 'static')
GUIDE_VIDEO_DIR = 'runtime/guide_videos'

# TMDB API configuration
TMDB_BASE_URL = 'https://api.themoviedb.org/3'

TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w500'

# Cache directory for TMDB results
CACHE_DIR = 'catalog/.tmdb_cache'
