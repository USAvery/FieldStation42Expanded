#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the custom program-guide page used as a channel or interactive guide overlay.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Custom Guide'
HIDE_FROM_MENU = True
STATIC_ALIASES = ['/static/customguide']

router = APIRouter()


@router.get('/static/customguide/customguide.html', name='customguide.index', include_in_schema=False)
def index(request: Request):
    """
    Render the customguide page
    """
    return bu.render_page(request, __name__)
