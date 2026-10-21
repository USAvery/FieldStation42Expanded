#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve the main console's remote-control page for channel, playback, volume, and guide commands.
"""
from fastapi import Request
from fastapi import APIRouter

router = APIRouter()


@router.get('/static/remote.html', include_in_schema=False)
@router.get('/remote', include_in_schema=False)
def index(request: Request):
    """
    Render the remote page
    """
    return request.app.state.templates.TemplateResponse(request=request, name='remote/index.html',
                                                        context={'title': 'Remote'})
