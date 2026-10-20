#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read and write scheduled blocks in the station database
"""
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager

from fs42.tools.media import title_parser
from fs42.tools.catalog import catalog_api
from fs42.tools.catalog import autobump_agent
from fs42.core.station_manager import StationManager
from fs42.tools.catalog.catalog_entry import CatalogEntry
from fs42.tools.schedule.block_plan import BlockPlanEntry
from fs42.tools.schedule.liquid_blocks import LiquidBlock
from fs42.tools.schedule.liquid_blocks import LiquidWebBlock
from fs42.tools.schedule.liquid_blocks import LiquidClipBlock
from fs42.tools.schedule.liquid_blocks import LiquidLoopBlock
from fs42.tools.schedule.liquid_blocks import LiquidOffAirBlock


def _build_block_from_row(row, content_cache=None):
    """
    Helper method to build a LiquidBlock from a database row
    If content_cache is provided, uses it for batch lookups instead of individual CatalogAPI calls.
    """
    _id = row[0]
    _station = row[1]
    _liquid_type = row[2]
    _start_time = datetime.fromisoformat(row[3])
    _end_time = datetime.fromisoformat(row[4])
    _break_strategy = row[5]
    _title = row[6]
    _sequence_key = json.loads(row[7]) if row[7] else None
    _break_info = json.loads(row[8]) if row[8] else None
    _content_json = json.loads(row[9]) if row[9] else None
    _plan_json = json.loads(row[10]) if row[10] else []

    content_obj = None
    if _content_json:
        if not isinstance(_content_json, list):
            # Single content entry
            if content_cache is not None:
                content_obj = content_cache.get(int(_content_json))
            else:
                content_obj = catalog_api.get_entry_by_id(int(_content_json))
        else:
            # Multiple content entries
            content_obj = []
            for entry in _content_json:
                if content_cache is not None:
                    cached_entry = content_cache.get(int(entry))
                    if cached_entry:
                        content_obj.append(cached_entry)
                else:
                    content_obj.append(catalog_api.get_entry_by_id(int(entry)))
    elif _liquid_type == 'LiquidWebBlock':
        jobj = _plan_json[0]
        content_obj = CatalogEntry(jobj['path'], jobj['duration'], autobump_agent.tag_str)

    main_normal = StationManager().server_conf.get('normalize_titles', True)
    the_title = _title

    if main_normal:
        custom_patterns = StationManager().server_conf.get('title_patterns', [])
        the_title = title_parser.parse_title(the_title, custom_patterns)

    args = (
        content_obj,
        _start_time,
        _end_time,
        the_title,  # title
        _break_strategy,  # break_strategy
        _break_info,
    )

    block = _block_factory(_liquid_type, args)
    block.sequence_key = _sequence_key

    plans = []
    for p in _plan_json:
        plans.append(
            BlockPlanEntry(p['path'], p['skip'], p['duration'], p['is_stream'], p.get('content_type', 'feature'),
                           p.get('media_type', 'video')))
    block.plan = plans
    return block


def _block_factory(liquid_type, args):
    """
    Block factory
    """
    match liquid_type:
        case 'LiquidBlock':
            return LiquidBlock(*args)
        case 'LiquidOffAirBlock':
            return LiquidOffAirBlock(*args)
        case 'LiquidClipBlock':
            return LiquidClipBlock(*args)
        case 'LiquidLoopBlock':
            return LiquidLoopBlock(*args)
        case 'LiquidWebBlock':
            return LiquidWebBlock(*args)
        case _:
            raise ValueError('Unknown liquid type: {}'.format(liquid_type))


class LiquidIO(object):
    """
    LiquidIO is a class that handles the input and output of liquid data
    It provides methods to read and write liquid data to a database.
    """

    def __init__(self):
        """
        Initialize the instance
        """
        self.db_path = StationManager().server_conf['db_path']
        self._init_liquid_table()

    @contextmanager
    def _get_connection(self):
        """
        Get connection
        """
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_liquid_table(self):
        """
        Creates a database table to hold liquid data
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""CREATE TABLE IF NOT EXISTS liquid_blocks (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                station TEXT NOT NULL,
                                liquid_type TEXT NOT NULL,
                                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                end_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                break_strategy TEXT NOT NULL,
                                title TEXT NOT NULL,
                                sequence_key TEXT,
                                break_info TEXT,
                                content_json TEXT NOT NULL,
                                plan_json TEXT NOT NULL
                            )""")

            # Create indexes for performance
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_liquid_blocks_station
                            ON liquid_blocks(station)""")
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_liquid_blocks_station_time
                            ON liquid_blocks(station, start_time, end_time)""")
            # Supports window queries that span every station (see query_all_liquid_blocks)
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_liquid_blocks_time
                            ON liquid_blocks(start_time, end_time)""")

            cursor.close()
            connection.commit()

    def get_liquid_blocks(self, station_name):
        """
        Retrieve liquid blocks from the database for a given station
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM liquid_blocks WHERE station = ? ORDER BY start_time', (station_name, ))
            rows = cursor.fetchall()
            cursor.close()

            # Collect all content IDs for batch lookup
            content_ids = set()
            for row in rows:
                content_json = json.loads(row[9]) if row[9] else None
                if content_json:
                    if isinstance(content_json, list):
                        content_ids.update(content_json)
                    else:
                        content_ids.add(content_json)

            # Batch fetch all content entries
            content_cache = catalog_api.get_entries_by_ids(list(content_ids)) if content_ids else {}

            # Build blocks with cached content
            liquid_blocks = []
            for row in rows:
                block = _build_block_from_row(row, content_cache)
                liquid_blocks.append(block)

            return liquid_blocks

    def query_liquid_blocks(self, station_name, start, end):
        """
        Query liquid blocks
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT * FROM liquid_blocks WHERE station = ? AND start_time < ? AND end_time > ? ORDER BY start_time',
                (station_name, end, start),
            )
            rows = cursor.fetchall()
            cursor.close()

            # Collect all content IDs for batch lookup
            content_ids = set()
            for row in rows:
                content_json = json.loads(row[9]) if row[9] else None
                if content_json:
                    if isinstance(content_json, list):
                        content_ids.update(content_json)
                    else:
                        content_ids.add(content_json)

            # Batch fetch all content entries
            content_cache = catalog_api.get_entries_by_ids(list(content_ids)) if content_ids else {}

            # Build blocks with cached content
            liquid_blocks = []
            for row in rows:
                block = _build_block_from_row(row, content_cache)
                liquid_blocks.append(block)

            return liquid_blocks

    def query_all_liquid_blocks(self, start, end):
        """
        Query all liquid blocks
        """

        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT * FROM liquid_blocks WHERE start_time < ? AND end_time > ? ORDER BY station, start_time',
                (end, start),
            )
            rows = cursor.fetchall()
            cursor.close()

            # Collect content IDs across every station for one batch lookup
            content_ids = set()
            for row in rows:
                content_json = json.loads(row[9]) if row[9] else None
                if content_json:
                    if isinstance(content_json, list):
                        content_ids.update(content_json)
                    else:
                        content_ids.add(content_json)

            content_cache = catalog_api.get_entries_by_ids(list(content_ids)) if content_ids else {}

            by_station = {}
            for row in rows:
                block = _build_block_from_row(row, content_cache)
                by_station.setdefault(row[1], []).append(block)

            return by_station

    def put_liquid_blocks(self, station_name, liquid_blocks):
        """
        Store liquid blocks in the database
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            for block in liquid_blocks:

                if block.content and not isinstance(block.content, list):
                    content_json = json.dumps(block.content.dbid)

                elif block.content:
                    content_json = json.dumps([c.dbid for c in block.content])
                else:
                    content_json = None

                # plan_json = json.dumps(block.plan.to_json()) if block.plan else None
                plan_json = json.dumps([p.to_json() for p in block.plan])
                block_type = type(block).__name__
                break_info = json.dumps(block.break_info) if block.break_info else None
                seq_json = json.dumps(block.sequence_key) if block.sequence_key else None

                cursor.execute(
                    """INSERT OR REPLACE INTO liquid_blocks 
                       (station, liquid_type, start_time, end_time, break_strategy, title, sequence_key, break_info, content_json, plan_json) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        station_name,
                        block_type,
                        block.start_time,
                        block.end_time,
                        block.break_strategy,
                        block.title,
                        seq_json,
                        break_info,
                        content_json,
                        plan_json,
                    ),
                )
            cursor.close()
            connection.commit()

    def delete_liquid_blocks(self, station_name):
        """
        Delete liquid blocks
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('DELETE FROM liquid_blocks WHERE station = ?', (station_name, ))
            cursor.close()
            connection.commit()

    def search_liquid_blocks(self, station_name, query):
        """
        Search liquid blocks by title for a given station
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM liquid_blocks WHERE station = ? AND title LIKE ? ORDER BY start_time',
                           (station_name, '%{}%'.format(query)))
            rows = cursor.fetchall()
            cursor.close()

        blocks = []
        for row in rows:
            blocks.append(_build_block_from_row(row))

        return blocks

    def search_all_liquid_blocks(self, query):
        """
        Search liquid blocks by title across all stations
        Returns a dictionary with station names as keys and lists of blocks as values.
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM liquid_blocks WHERE title LIKE ? ORDER BY station, start_time',
                           ('%{}%'.format(query), ))
            rows = cursor.fetchall()
            cursor.close()

        results = {}
        for row in rows:
            station = row[1]  # station is at index 1
            if station not in results:
                results[station] = []
            results[station].append(_build_block_from_row(row))

        return results
