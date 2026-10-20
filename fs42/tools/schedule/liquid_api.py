#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage liquid api
"""
from fs42.tools.schedule.liquid_io import LiquidIO


def add_blocks(station_config, blocks):
    """
    Add blocks
    """
    LiquidIO().put_liquid_blocks(station_config['network_name'], blocks)


def get_blocks(station_config, start=None, end=None):
    """
    Get blocks
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
    Delete blocks
    """
    LiquidIO().delete_liquid_blocks(station_config['network_name'])


def search_blocks(station_config, query):
    """
    Search blocks
    """
    return LiquidIO().search_liquid_blocks(station_config['network_name'], query)


def search_all_blocks(query):
    """
    Search all blocks
    """
    return LiquidIO().search_all_liquid_blocks(query)
