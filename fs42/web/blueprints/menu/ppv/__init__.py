#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the pay-per-view browsing page for selecting media to play.
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu

TITLE = 'Pay-Per-View'
HIDE_FROM_MENU = True
STATIC_ALIASES = ['/static/ppv']

router = APIRouter()


@router.get('/static/ppv/ppv.html', name='ppv.index', include_in_schema=False)
def index(request: Request):
    """
    Render the ppv page
    """
    return bu.render_page(request, __name__)
