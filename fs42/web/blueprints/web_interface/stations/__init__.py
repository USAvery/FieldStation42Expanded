#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the station-management dashboard with station filtering, duplication, and template selection.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Station Manager'
MENU_TITLE = 'Stations'
MENU_GROUP = 'Console'
MENU_ORDER = 40
HEADING = ''

router = APIRouter()


@router.get('/static/stations.html', name='stations.index', include_in_schema=False)
def index(request: Request):
    """
    Render the stations page
    """
    return bu.render_page(request, __name__)
