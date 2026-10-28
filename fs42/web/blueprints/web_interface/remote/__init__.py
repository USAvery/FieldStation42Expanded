#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the main console's remote-control page for channel, playback, volume, and guide commands.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Remote Control'
MENU_TITLE = 'Remote'
MENU_GROUP = 'Console'
MENU_ORDER = 50
HEADING = ''
REQUIRES_PLAYER = True

router = APIRouter()


@router.get('/static/remote.html', name='remote.index', include_in_schema=False)
@router.get('/remote', name='remote.index', include_in_schema=False)
def index(request: Request):
    """
    Render the remote page
    """
    return bu.render_page(request, __name__)
