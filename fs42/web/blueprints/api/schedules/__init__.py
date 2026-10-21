#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose station schedules and time-window searches as HTTP responses, attaching media metadata and
cached streaming-guide listings when requested.
"""
from datetime import datetime
from datetime import timedelta

from fastapi import status
from fastapi import APIRouter
from fastapi import HTTPException

from fs42.tools.media import metadata_io
from fs42.tools.schedule import liquid_api
from fs42.tools.epg.epg_cache import EpgCache
from fs42.core.station_manager import StationManager
from fs42.tools.epg import epg_cache as epg_cache_utils

router = APIRouter(prefix='/schedules', tags=['schedules'])


def _attach_meta(blocks):
    """
    Attach cached NFO/tag metadata to each single-content block in place

    Multi-content blocks (clip shows, loops) and off-air blocks have no single
    feature to describe, so they are left without a `meta` field and consumers
    fall back to the block title.
    """
    if not blocks:
        return blocks
    for block in blocks:
        content = getattr(block, 'content', None)
        if content is None or isinstance(content, list):
            continue
        path = getattr(content, 'path', None)
        if not path:
            continue
        meta = metadata_io.read(path)
        if meta:
            block.meta = meta
    return blocks


@router.get('/search_all')
async def search_all_schedules(query: str = None):
    """
    Search saved programming across stations or list all schedules when no query is supplied

    :param query: (str) optional schedule search text
    :response:    (jsn) matching blocks grouped by network, with any query errors
    """
    if not query:
        # If no query, get all blocks from all stations
        station_manager = StationManager()
        all_results = []

        for station in station_manager.stations:
            if station.get('_has_schedule', False):
                try:
                    schedule_blocks = liquid_api.get_blocks(station)
                    if schedule_blocks:
                        all_results.append({
                            'network_name': station['network_name'],
                            'schedule_blocks': schedule_blocks
                        })
                except Exception as e:
                    all_results.append({
                        'network_name': station['network_name'],
                        'error': str(e),
                        'schedule_blocks': []
                    })

        return {'query': query, 'results': all_results}
    else:
        # Search across all stations at once
        try:
            search_results = liquid_api.search_all_blocks(query)
            all_results = []

            for station_name, blocks in search_results.items():
                if blocks:
                    all_results.append({'network_name': station_name, 'schedule_blocks': blocks})

            return {'query': query, 'results': all_results}
        except Exception as e:
            return {'query': query, 'error': str(e), 'results': []}


@router.get('/search/{network_name}')
async def search_schedule(network_name: str, query: str = None):
    """
    Search one station's programming or list its entire saved schedule

    :param network_name: (str) active station name
    :param query:        (str) optional schedule search text
    :response:           (jsn) network, query, and matching schedule blocks
    """
    conf = StationManager().station_by_name(network_name)
    if conf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Station '{}' not found".format(network_name))
    if query:
        schedule_blocks = liquid_api.search_blocks(conf, query)
    else:
        schedule_blocks = liquid_api.get_blocks(conf)

    return {'network_name': network_name, 'query': query, 'schedule_blocks': schedule_blocks}


def _attach_meta_batch(by_station):
    """
    Attach metadata to every block across every station on one connection
    """

    def single_content_path(block):
        """
        Return the media path for a single-item program block, excluding clip collections
        """
        content = getattr(block, 'content', None)
        if content is None or isinstance(content, list):
            return None
        return getattr(content, 'path', None)

    paths = []
    for blocks in by_station.values():
        for block in blocks:
            path = single_content_path(block)
            if path:
                paths.append(path)

    if not paths:
        return

    metas = metadata_io.read_many(paths)
    for blocks in by_station.values():
        for block in blocks:
            path = single_content_path(block)
            if path and path in metas:
                block.meta = metas[path]


def _listing_projection(blocks, include_meta):
    """
    Reduce schedule blocks to guide listings with metadata-derived titles

    :param blocks:       (list) loaded programming blocks with optional attached metadata
    :param include_meta: (bool) whether to retain metadata in each listing
    :return:             (list) title and ISO start/end dictionaries
    """
    # only get the stuff we need
    listings = []
    for block in blocks:
        meta = getattr(block, 'meta', None)
        listing = {
            'title': metadata_io.pick_title(meta) or block.title,
            'start_time': block.start_time.isoformat(),
            'end_time': block.end_time.isoformat(),
        }
        if include_meta and meta:
            listing['meta'] = meta
        listings.append(listing)
    return listings


# NOTE: must stay above /{network_name}, or that route captures "all".
@router.get('/all')
def get_all_schedules(start: str = None, end: str = None, include_meta: bool = False):
    """
    Combine local schedules and cached external EPG listings for a requested time window

    :param start:        (str) required ISO-format window start
    :param end:          (str) required ISO-format window end
    :param include_meta: (bool) whether listings should include cached program metadata
    :response:           (jsn) listings indexed by network, or a date-input error
    """

    if not start or not end:
        return {'error': 'start and end are both required.'}

    try:
        sdt = datetime.fromisoformat(start)
        edt = datetime.fromisoformat(end)
    except ValueError:
        return {'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS) for start and end.'}

    by_station = liquid_api.get_all_blocks(sdt, edt)

    # Always attach metadata: even when include_meta is off, the listing
    # title still prefers metadata over the filename-parsed title.
    _attach_meta_batch(by_station)

    schedules = {name: _listing_projection(blocks, include_meta) for name, blocks in by_station.items()}

    # Streaming stations use a prebuilt local SQLite EPG cache. This adds no
    # network or XML work to guide rendering; the guide still receives one
    # batched response for the visible window.
    epg_schedules = EpgCache().get_all_listings(
        StationManager().stations,
        sdt,
        edt,
        include_meta=include_meta,
    )
    schedules.update(epg_schedules)

    return {'start': start, 'end': end, 'schedules': schedules}


@router.get('/{network_name}')
async def get_schedule(network_name: str, start: str = None, end: str = None, include_meta: bool = False):
    """
    Read a station's saved programming or mapped external EPG listings

    :param network_name: (str) active station name
    :param start:        (str) optional ISO-format window start, used with end
    :param end:          (str) optional ISO-format window end, used with start
    :param include_meta: (bool) whether to attach cached program metadata
    :response:           (jsn) station schedule blocks or cached EPG listings
    """
    conf = StationManager().station_by_name(network_name)
    if conf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Station '{}' not found".format(network_name))
    sdt = None
    edt = None
    if start and end:
        try:
            sdt = datetime.fromisoformat(start)
            edt = datetime.fromisoformat(end)
        except ValueError:
            return {'error': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS) for start and end.'}

    if epg_cache_utils.station_enabled(conf):
        if sdt is None or edt is None:
            now = datetime.now()
            sdt = now - timedelta(hours=6)
            edt = now + timedelta(days=2)

        schedule_blocks = EpgCache().get_station_listings(
            conf,
            sdt,
            edt,
            include_meta=include_meta,
        )
        return {
            'network_name': network_name,
            'schedule_blocks': schedule_blocks,
        }

    schedule_blocks = liquid_api.get_blocks(conf, sdt, edt)
    if include_meta:
        _attach_meta(schedule_blocks)
    return {'network_name': network_name, 'schedule_blocks': schedule_blocks}
