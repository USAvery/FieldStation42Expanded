#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose the package interface
"""
from fastapi import APIRouter

from .ppv import router as ppv_router
from .build import router as build_router
from .media import router as media_router
from .player import router as player_router
from .themes import router as themes_router
from .summary import router as summary_router
from .catalogs import router as catalogs_router
from .stations import router as stations_router
from .schedules import router as schedules_router

# Create a list of all routers to be included
routers = [
    summary_router,
    catalogs_router,
    schedules_router,
    player_router,
    build_router,
    themes_router,
    stations_router,
    ppv_router,
    media_router,
]
