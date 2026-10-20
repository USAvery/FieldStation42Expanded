#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose the package interface
"""
from fastapi import Request
from fastapi import APIRouter

router = APIRouter()


@router.get('/static/diagnostics.html', include_in_schema=False)
def index(request: Request):
    """
    Render the diagnostics page
    """
    return request.app.state.templates.TemplateResponse(request=request, name='diagnostics/index.html',
                                                        context={'title': 'Diagnostics'})
