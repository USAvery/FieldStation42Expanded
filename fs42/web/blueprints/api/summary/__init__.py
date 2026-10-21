#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose channel lists and station, catalog, and schedule summaries for the web console.
"""
from fastapi import APIRouter

from fs42.tools.catalog import catalog_api
from fs42.tools.epg.epg_cache import EpgCache
from fs42.core.station_manager import StationManager
from fs42.tools.epg import epg_cache as epg_cache_utils
from fs42.tools.schedule.liquid_manager import LiquidManager

router = APIRouter(prefix='/summary', tags=['summary'])


@router.get('/')
async def get_summary():
    """
    Combine station identity, catalog totals, and schedule coverage for the console overview
    """
    summaries = []
    for station in StationManager().stations:
        if station['_has_schedule']:
            sched_summary = LiquidManager().get_summary_json(network_name=station['network_name'])
        else:
            sched_summary = {'network_name': station['network_name'], 'start': 0, 'end': 0}
        summary = {
            'network_name': station['network_name'],
            'network_long_name': station.get('network_long_name', ''),
            'channel_number': station['channel_number'],
            '_has_schedule': station['_has_schedule'],
            'hidden': station.get('hidden', False),
            'catalog_summary': catalog_api.get_summary(station),
            'schedule_summary': sched_summary,
        }
        summaries.append(summary)
    return {'summary_data': summaries}


@router.get('/channels')
def get_channels():
    """
    List active channel identities and whether local or external guide data is available
    """
    # Minimal station listing for the guide
    channels = [{
        'network_name': station['network_name'],
        'network_long_name': station.get('network_long_name', ''),
        'channel_number': station['channel_number'],
        'hidden': station.get('hidden', False),
        'has_schedule': (station.get('_has_schedule', False) or epg_cache_utils.station_enabled(station)),
    } for station in StationManager().stations]
    return {'channels': channels}


@router.get('/stations')
async def get_stations():
    """
    List the network names currently loaded in the station registry
    """
    station_ids = [station['network_name'] for station in StationManager().stations]
    return {'network_names': station_ids}


@router.get('/schedules')
async def get_schedule_summaries():
    """
    Return the loaded networks' schedule start and end boundaries
    """
    summaries = LiquidManager().get_summary_json()
    return {'schedule_summaries': summaries}


@router.get('/schedules/{network_name}')
async def get_schedule_summary(network_name: str):
    """
    Return one network's schedule coverage or an error if it does not support scheduling
    """
    station = StationManager().station_by_name(network_name)
    if station['_has_schedule']:
        summary = LiquidManager().get_summary_json(network_name=network_name)
        return {'schedule_summary': summary}
    else:
        return {'error': 'No schedule found for network {}'.format(network_name)}


@router.get('/catalogs')
async def get_catalog_summary():
    """
    Count stored catalog entries for every active station
    """
    summaries = []
    for station in StationManager().stations:
        catalog_entries = catalog_api.get_entries(station)
        summary = {'network_name': station['network_name'], 'entry_count': len(catalog_entries)}
        summaries.append(summary)
    return {'catalog_summaries': summaries}
