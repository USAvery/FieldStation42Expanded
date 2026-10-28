#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the web-console home dashboard at the root and its existing static-page URL.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'FieldStation42'
MENU_TITLE = 'Home'
MENU_GROUP = 'Console'
MENU_ORDER = 0
HEADING = ''

router = APIRouter()


@router.get('/static/index.html', name='index.index', include_in_schema=False)
@router.get('/', name='index.index', include_in_schema=False)
def index(request: Request):
    """
    Render the index page
    """
    return bu.render_page(request, __name__)
