#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose the package interface
"""
from fs42.web.blueprints.tools.ppv import router as ppv_router
from fs42.web.blueprints.tools.bump import router as bump_router
from fs42.web.blueprints.tools.about import router as about_router
from fs42.web.blueprints.tools.guide import router as guide_router
from fs42.web.blueprints.tools.index import router as index_router
from fs42.web.blueprints.tools.remote import router as remote_router
from fs42.web.blueprints.tools.catalog import router as catalog_router
from fs42.web.blueprints.tools.schedule import router as schedule_router
from fs42.web.blueprints.tools.stations import router as stations_router
from fs42.web.blueprints.tools.customguide import router as customguide_router
from fs42.web.blueprints.tools.diagnostics import router as diagnostics_router
from fs42.web.blueprints.tools.guide_frame import router as guide_frame_router
from fs42.web.blueprints.tools.station_editor import router as station_editor_router

routers = [
    about_router, catalog_router, diagnostics_router, guide_router, guide_frame_router, index_router,
    remote_router, schedule_router, stations_router, station_editor_router, bump_router, customguide_router,
    ppv_router
]
