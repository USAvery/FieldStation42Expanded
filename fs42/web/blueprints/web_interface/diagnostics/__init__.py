#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the browser diagnostics display for player status and host information.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Diagnostics'
HIDE_FROM_MENU = True

router = APIRouter()


@router.get('/static/diagnostics.html', name='diagnostics.index', include_in_schema=False)
def index(request: Request):
    """
    Render the diagnostics page
    """
    return bu.render_page(request, __name__)
