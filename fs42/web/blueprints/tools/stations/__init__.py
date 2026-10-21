#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the station-management dashboard with station filtering, duplication, and template selection.
"""
from fastapi import Request
from fastapi import APIRouter

router = APIRouter()


@router.get('/static/stations.html', include_in_schema=False)
def index(request: Request):
    """
    Render the stations page
    """
    return request.app.state.templates.TemplateResponse(request=request, name='stations/index.html',
                                                        context={'title': 'Stations'})
