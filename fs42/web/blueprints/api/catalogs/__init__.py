#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose station catalog retrieval and searches across one or all catalogs as HTTP endpoints.
"""
from fastapi import APIRouter

from fs42.tools.catalog import catalog_api
from fs42.core.station_manager import StationManager

router = APIRouter(prefix='/catalogs', tags=['catalogs'])


@router.get('/search_all')
async def search_all_catalogs(query: str = None):
    """
    Search media catalogs across catalog-enabled stations

    :param query: (str) optional title, tag, or path search text
    :response:    (jsn) matching entries grouped by network, including per-station errors
    """
    station_manager = StationManager()
    all_results = []

    for station in station_manager.stations:
        if station.get('_has_catalog', False):
            try:
                if query:
                    catalog_entries = catalog_api.search_entries(station, query)
                else:
                    catalog_entries = catalog_api.get_entries(station)

                if catalog_entries:
                    all_results.append({
                        'network_name': station['network_name'],
                        'catalog_entries': catalog_entries
                    })
            except Exception as e:
                all_results.append({
                    'network_name': station['network_name'],
                    'error': str(e),
                    'catalog_entries': []
                })

    return {'query': query, 'results': all_results}


@router.get('/{network_name}')
async def get_catalog(network_name: str):
    """
    Read every stored catalog entry for a network

    :param network_name: (str) active network name
    :response:           (jsn) network name and catalog entries
    """
    conf = StationManager().station_by_name(network_name)
    catalog_entries = catalog_api.get_entries(conf)
    return {'network_name': network_name, 'catalog_entries': catalog_entries}


@router.get('/search/{network_name}')
async def search_catalog(network_name: str, query: str = None):
    """
    Search a network's catalog or return all entries when the query is empty

    :param network_name: (str) active network name
    :param query:        (str) optional title, tag, or path search text
    :response:           (jsn) network name, query, and matching entries
    """
    conf = StationManager().station_by_name(network_name)
    if query:
        catalog_entries = catalog_api.search_entries(conf, query)
    else:
        catalog_entries = catalog_api.get_entries(conf)

    return {'network_name': network_name, 'query': query, 'catalog_entries': catalog_entries}
