#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Validate HTTP requests to list, create, update, and delete station configuration files and return
structured station responses.
"""
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from fastapi import status
from pydantic import Field
from fastapi import APIRouter
from pydantic import BaseModel
from fastapi import HTTPException

from fs42.core.station_io import StationIO
from fs42.core.station_manager import StationManager
from fs42.tools.schedule.liquid_manager import LiquidManager

router = APIRouter(prefix='/stations', tags=['stations'])


# Pydantic Models
class StationConfigRequest(BaseModel):
    """
    Accept a wrapped station configuration for create and update requests
    """
    station_conf: Dict[str, Any] = Field(
        ...,
        description='Station configuration object containing network_name, channel_number, and other settings')

    class Config(object):
        """
        Provide a station configuration example for the generated API schema
        """
        json_schema_extra = {
            'example': {
                'station_conf': {
                    'network_name': 'MyChannel',
                    'channel_number': 42,
                    'network_type': 'standard',
                    'schedule_increment': 30
                }
            }
        }


class StationConfigResponse(BaseModel):
    """
    Describe a station-file operation's result and optional saved station details
    """
    success: bool
    message: str
    network_name: Optional[str] = None
    channel_number: Optional[int] = None
    file_path: Optional[str] = None


class StationListResponse(BaseModel):
    """
    Return saved station documents together with their count
    """
    count: int
    stations: List[Dict[str, Any]]


class ErrorResponse(BaseModel):
    """
    Describe an unsuccessful station operation with optional diagnostic detail
    """
    success: bool = False
    error: str
    details: Optional[str] = None


# Endpoints


@router.get('', response_model=StationListResponse)
async def list_stations():
    """
    List saved station documents and annotate configurations excluded from the active registry

    :response: (jsn) station count and raw documents with draft reasons where applicable
    """
    station_io = StationIO()
    raw_stations = station_io.list_raw_station_configs()

    skipped_by_name = {
        entry['network_name']: entry['error']
        for entry in StationManager().skipped_stations if entry['network_name']
    }

    for raw in raw_stations:
        station_conf = raw.get('station_conf')
        if not isinstance(station_conf, dict):
            continue
        reason = skipped_by_name.get(station_conf.get('network_name'))
        if reason:
            station_conf['_draft'] = True
            station_conf['_draft_reason'] = reason

    return {'count': len(raw_stations), 'stations': raw_stations}


@router.get('/{network_name}')
async def get_station_config(network_name: str):
    """
    Read a station's raw saved configuration for editing

    :param network_name: (str) exact stored network name
    :response:           (jsn) station name and unexpanded configuration document
    """

    station_io = StationIO()
    success, raw_data, error_msg = station_io.read_raw_station_config(network_name)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)

    return {'network_name': network_name, 'station_config': raw_data}


@router.post('', response_model=StationConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_station(config: StationConfigRequest):
    """
    Validate and save a new station, then refresh station and schedule state

    :param config: (StationConfigRequest) new wrapped station settings
    :response:     (jsn) creation result and saved file details
    """

    station_manager = StationManager()

    # Extract network_name for checking
    if 'network_name' not in config.station_conf:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='network_name is required in station_conf')

    network_name = config.station_conf['network_name']

    if StationIO().find_config_by_network_name(network_name) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Station '{}' already exists. Use PUT to update.".format(network_name))

    # Write the configuration (StationManager handles validation and file I/O via StationIO)
    success, message, file_path = station_manager.write_station_config(network_name, config.model_dump(),
                                                                       is_update=False)

    if success:
        LiquidManager().reload_schedules()

    if not success:
        # Determine if it's a validation error or conflict
        if 'already used' in message or 'already exists' in message:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return {
        'success': True,
        'message': message,
        'network_name': network_name,
        'channel_number': config.station_conf.get('channel_number'),
        'file_path': file_path
    }


@router.put('/{network_name}', response_model=StationConfigResponse)
async def update_station(network_name: str, config: StationConfigRequest):
    """
    Replace an existing station configuration, supporting renames and channel changes

    :param network_name: (str) existing stored network name
    :param config:       (StationConfigRequest) replacement wrapped station settings
    :response:           (jsn) update result and saved file details
    """
    station_manager = StationManager()

    if StationIO().find_config_by_network_name(network_name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Station '{}' not found".format(network_name))

    # Write the configuration (update mode, StationManager handles validation and file I/O via StationIO)
    success, message, file_path = station_manager.write_station_config(network_name, config.model_dump(),
                                                                       is_update=True)

    if success:
        LiquidManager().reload_schedules()

    if not success:
        # Determine if it's a validation error or conflict
        if 'already used' in message or 'already exists' in message:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    new_network_name = config.station_conf.get('network_name', network_name)

    return {
        'success': True,
        'message': message,
        'network_name': new_network_name,
        'channel_number': config.station_conf.get('channel_number'),
        'file_path': file_path
    }


@router.delete('/{network_name}', response_model=StationConfigResponse)
async def delete_station(network_name: str):
    """
    Delete a station's saved configuration and refresh active station and schedule state

    :param network_name: (str) stored network name to remove
    :response:           (jsn) deletion result and removed network name
    """

    station_manager = StationManager()

    if StationIO().find_config_by_network_name(network_name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Station '{}' not found".format(network_name))

    # Delete the configuration (StationManager handles file deletion via StationIO)
    success, message = station_manager.delete_station_config(network_name)

    if success:
        LiquidManager().reload_schedules()

    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)

    return {'success': True, 'message': message, 'network_name': network_name}
