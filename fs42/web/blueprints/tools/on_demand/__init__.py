#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Render the Comcast-style On Demand library menu
"""
from fastapi import Request
from fastapi import APIRouter


router = APIRouter()


@router.get('/on-demand', include_in_schema=False)
@router.get('/static/on_demand/on_demand.html', include_in_schema=False)
def get_page(request: Request):
    """
    Open the local movie and episode browser in the persistent guide renderer
    """
    return request.app.state.templates.TemplateResponse(request=request, name='on_demand/index.html',
                                                        context={'title': 'On Demand'})
