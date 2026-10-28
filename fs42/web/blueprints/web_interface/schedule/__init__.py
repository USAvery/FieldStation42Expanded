#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the schedule-management page for inspecting programming and requesting schedule builds or
extensions.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Schedule Manager'
MENU_TITLE = 'Schedule'
MENU_GROUP = 'Console'
MENU_ORDER = 20
HEADING = 'Schedule Manager'

router = APIRouter()


@router.get('/static/schedule.html', name='schedule.index', include_in_schema=False)
def index(request: Request):
    """
    Render the schedule page
    """
    return bu.render_page(request, __name__)
