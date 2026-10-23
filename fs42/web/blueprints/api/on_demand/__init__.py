#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Serve paginated local On Demand listings and queue validated, single-title playback
"""
from fastapi import Query
from fastapi import Request
from fastapi import APIRouter
from fastapi import HTTPException

from fs42.tools.on_demand import OnDemand
from fs42.tools.on_demand._constants import CATEGORIES


router = APIRouter(prefix='/on-demand', tags=['on-demand'])


@router.get('/menu')
def get_menu():
    """
    List the menu categories and active catalog channels
    """
    return OnDemand().get_menu()


@router.post('/open')
def open_menu(request: Request):
    """
    Open the On Demand menu directly from a remote without interrupting the current channel
    """
    queue = request.app.state.player_command_queue
    if queue is None:
        raise HTTPException(status_code=503, detail='The player is not connected.')
    queue.put({'command': 'on_demand_menu'})
    return {'success': True}


@router.get('/titles')
def get_titles(category: str = 'all', query: str = Query('', max_length=200),
               channel: str = '', page: int = Query(0, ge=0)):
    """
    Return a bounded page of movies and episodes matching the chosen menu or search
    """
    if category not in {item['id'] for item in CATEGORIES}:
        raise HTTPException(status_code=400, detail='Unknown library category')
    return OnDemand().get_titles(category, query, channel, page)


@router.post('/play/{entry_id}')
def play_title(entry_id: int, request: Request):
    """
    Validate a catalog selection and ask the existing player to play it once
    """
    try:
        OnDemand().get_selection(entry_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    queue = request.app.state.player_command_queue
    if queue is None:
        raise HTTPException(status_code=503, detail='The player is not connected. Start FieldStation42 and retry.')
    queue.put({'command': 'on_demand', 'entry_id': entry_id})
    return {'success': True}
