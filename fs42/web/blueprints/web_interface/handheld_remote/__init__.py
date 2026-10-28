#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the standalone handheld remote page and compatibility asset URLs
"""
import os

from fastapi import Request
from fastapi import APIRouter

from fastapi.responses import FileResponse

from fs42.web.core import _constants
from fs42.web.core import blueprint as bu

TITLE = 'FieldStation42 TV Remote'
HIDE_FROM_MENU = True
STANDALONE = True
SHARED_UTILS = False

router = APIRouter()


@router.get('/', name='handheld_remote.index', include_in_schema=False)
@router.get('/static/index.html', name='handheld_remote.index', include_in_schema=False)
def index(request: Request):
    """
    Render the standalone remote
    """
    return bu.render_page(request, __name__)


@router.get('/static/remote.js', include_in_schema=False)
def get_script():
    """
    Preserve the remote script URL
    """
    return FileResponse(
        os.path.join(_constants.WEB_DIR, 'blueprints', 'web_interface', 'handheld_remote', 'static', 'handheld_remote.js'))


@router.get('/static/remote.css', include_in_schema=False)
def get_stylesheet():
    """
    Preserve the remote stylesheet URL
    """
    return FileResponse(
        os.path.join(_constants.WEB_DIR, 'blueprints', 'web_interface', 'handheld_remote', 'static', 'style.css'))
