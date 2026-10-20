#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Validate remote requests and dispatch player commands
"""
from fastapi import APIRouter
from pydantic import BaseModel
from pydantic import validator
from fastapi import HTTPException

from fs42.tools.field_player import remote_commands
from fs42.web.blueprints.api.remote_control import _constants

router = APIRouter()


class CommandPayload(BaseModel):
    """
    CommandPayload
    """
    command: str
    channel: int

    @validator('command')
    def validate_command(cls, v):
        """
        Validate command
        """
        if v not in _constants.ALLOWED_COMMANDS:
            raise ValueError('Invalid command: {}'.format(v))
        return v


@router.post('/api/command')
async def handle_command(payload: CommandPayload):
    """
    Handle command
    """
    try:
        status = remote_commands.write_command(payload.dict())

        return {'status': 'ok', 'current': status}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/api/status')
def get_status():
    """
    Get status
    """
    return remote_commands.read_status()
