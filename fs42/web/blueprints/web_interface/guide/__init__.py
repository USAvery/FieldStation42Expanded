#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the console page that hosts the television program-guide display.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Guide'
MENU_TITLE = 'Guide'
MENU_GROUP = 'Console'
MENU_ORDER = 30
HEADING = 'Guide'

router = APIRouter()


@router.get('/static/guide.html', name='guide.index', include_in_schema=False)
def index(request: Request):
    """
    Render the guide page
    """
    return bu.render_page(request, __name__)
