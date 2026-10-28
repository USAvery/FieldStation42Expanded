#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Render the Comcast-style On Demand library menu
"""
from fastapi import Request
from fastapi import APIRouter

from fs42.web.core import blueprint as bu


TITLE = 'Comcast On Demand'
HIDE_FROM_MENU = True
STATIC_ALIASES = ['/static/on_demand']

router = APIRouter()


@router.get('/on-demand', name='on_demand.index', include_in_schema=False)
@router.get('/static/on_demand/on_demand.html', name='on_demand.index', include_in_schema=False)
def get_page(request: Request):
    """
    Open the local movie and episode browser in the persistent guide renderer
    """
    return bu.render_page(request, __name__)
