#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the console's About page with its theme and display-preference controls.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'About FieldStation42'
MENU_TITLE = 'About'
MENU_GROUP = 'Console'
MENU_ORDER = 60
HEADING = 'About FieldStation42'

router = APIRouter()


@router.get('/static/about.html', name='about.index', include_in_schema=False)
def index(request: Request):
    """
    Render the about page
    """
    return bu.render_page(request, __name__)
