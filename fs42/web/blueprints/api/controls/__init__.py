# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""One validated dispatch boundary for controls, independent of buttons and layouts."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from fs42.core.controls import ACTIONS, FILE_COMMANDS, control_manifest
from fs42.tools.field_player import remote_commands
from fs42.web.blueprints.api import player

router = APIRouter(prefix='/controls', tags=['controls'])
SHARED = True


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)


@router.get('')
def get_controls(request: Request):
    return control_manifest(request.app.state.control_transport)


@router.post('/dispatch')
async def dispatch(payload: ControlRequest, request: Request):
    action = ACTIONS.get(payload.action)
    if action is None:
        raise HTTPException(status_code=422, detail='Unknown control action: ' + payload.action)
    try:
        message = action.message(payload.arguments)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if request.app.state.control_transport == 'file':
        if action.command not in FILE_COMMANDS:
            raise HTTPException(status_code=503, detail='This control is unavailable on the standalone remote.')
        result = await run_in_threadpool(remote_commands.write_command, message)
    elif action.service:
        # Only catalog-owned service names can be called; the request never supplies one.
        result = await getattr(player, action.service)()
    else:
        queue = getattr(request.app.state, 'player_command_queue', None)
        if queue is None:
            raise HTTPException(status_code=503, detail='The player is not connected.')
        queue.put(message)
        result = {'status': 'ok'}
    return {'action': action.name, 'result': result}
