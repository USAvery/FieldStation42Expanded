#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Provide database-backed insertion, deletion, retrieval, and time-window searches for station
schedule blocks.
"""
from fs42.tools.schedule.liquid_io import LiquidIO


def add_blocks(station_config, blocks):
    """
    Persist the supplied programming blocks under the configured network name
    """
    LiquidIO().put_liquid_blocks(station_config['network_name'], blocks)


def get_blocks(station_config, start=None, end=None):
    """
    Read a station's saved blocks, optionally restricting them to an overlapping time window

    :param station_config: (dict) station settings identifying the network
    :param start:          (datetime) optional window start, used together with end
    :param end:            (datetime) optional window end, used together with start
    :return:               (list) matching blocks, or None when station settings are absent
    """
    if not station_config:
        return None
    if not start and not end:
        return LiquidIO().get_liquid_blocks(station_config['network_name'])
    else:
        # If start and end are provided, filter the blocks accordingly
        return LiquidIO().query_liquid_blocks(station_config['network_name'], start, end)


def get_all_blocks(start, end):
    """
    Blocks for every station in a window, keyed by network name
    """
    return LiquidIO().query_all_liquid_blocks(start, end)


def delete_blocks(station_config):
    """
    Delete every saved programming block for the configured network
    """
    LiquidIO().delete_liquid_blocks(station_config['network_name'])


def search_blocks(station_config, query):
    """
    Search saved programming for one station using its schedule storage search
    """
    return LiquidIO().search_liquid_blocks(station_config['network_name'], query)


def search_all_blocks(query):
    """
    Search saved programming across all stations
    """
    return LiquidIO().search_all_liquid_blocks(query)
