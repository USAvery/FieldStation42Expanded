#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read and write catalog entries in the station database
"""
import os
import json
import logging
import sqlite3
from contextlib import contextmanager

from fs42.core import logger as project_logger
from fs42.core.station_manager import StationManager
from fs42.tools.catalog.catalog_entry import CatalogEntry
from fs42.tools.catalog import catalog_entry as catalog_entry_utils

_logger = project_logger.setup('fs42.tools.catalog.catalog_io')


class CatalogIO(object):
    """
    CatalogIO
    """

    def __init__(self):
        """
        Initialize the instance
        """
        self.db_path = StationManager().server_conf['db_path']
        self._l = logging.getLogger('CATIO')
        self._init_catalog_table()

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

    def _init_catalog_table(self):
        """
        Creates a database table to hold CatalogEntry records
        Each record is associated with a station (text string).
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            # Create the table with new schema
            cursor.execute("""CREATE TABLE IF NOT EXISTS catalog_entries (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                station TEXT NOT NULL,
                                path TEXT NOT NULL,
                                title TEXT NOT NULL,
                                duration REAL NOT NULL,
                                tag TEXT NOT NULL,
                                count INTEGER DEFAULT 0,
                                hints TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                realpath TEXT,
                                content_type TEXT DEFAULT 'feature',
                                UNIQUE(station, tag, path)
                                )
                            """)

            # Check if realpath column exists, add it if it doesn't
            cursor.execute('PRAGMA table_info(catalog_entries)')
            columns = [column[1] for column in cursor.fetchall()]

            if 'realpath' not in columns:
                self._l.info('Adding realpath column to catalog_entries table')
                cursor.execute('ALTER TABLE catalog_entries ADD COLUMN realpath TEXT')

                # Populate realpath for existing entries
                cursor.execute('SELECT id, path FROM catalog_entries WHERE realpath IS NULL')
                rows = cursor.fetchall()
                for row_id, path in rows:
                    try:
                        realpath = os.path.realpath(path)
                        cursor.execute('UPDATE catalog_entries SET realpath = ? WHERE id = ?', (realpath, row_id))
                    except Exception as e:
                        self._l.warning('Could not compute realpath for {0}: {1}'.format(path, e))

                connection.commit()
                self._l.info('Updated realpath for {} existing entries'.format(len(rows)))

            if 'content_type' not in columns:
                self._l.info('Adding content_type column to catalog_entries table')
                cursor.execute("ALTER TABLE catalog_entries ADD COLUMN content_type TEXT DEFAULT 'feature'")
                connection.commit()
                self._l.info('Added content_type column to catalog_entries table')

            if 'media_type' not in columns:
                self._l.info('Adding media_type column to catalog_entries table')
                cursor.execute("ALTER TABLE catalog_entries ADD COLUMN media_type TEXT DEFAULT 'video'")
                connection.commit()
                self._l.info('Added media_type column to catalog_entries table')

            # Create indexes
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_catalog_station 
                            ON catalog_entries(station)""")
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_catalog_tag 
                            ON catalog_entries(tag)""")
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_catalog_path
                    ON catalog_entries(path)""")
            cursor.execute("""CREATE INDEX IF NOT EXISTS idx_catalog_tag_duration_count
                    ON catalog_entries(station, tag, duration, count)""")

            cursor.close()

    def entry_by_id(self, entry_id):
        """
        Entry by id
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT * FROM catalog_entries
                              WHERE id = ?""",
                (entry_id, ),
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return catalog_entry_utils.from_db_row(row)

            return None

    def entries_by_ids(self, entry_ids):
        """
        Batch lookup of catalog entries by IDs
        Returns a dictionary mapping entry_id -> CatalogEntry for found entries.
        """
        if not entry_ids:
            return {}

        with self._get_connection() as connection:
            cursor = connection.cursor()
            # Create placeholders for IN clause
            placeholders = ','.join('?' * len(entry_ids))
            cursor.execute(
                'SELECT * FROM catalog_entries\n                   WHERE id IN ({})'.format(placeholders),
                entry_ids,
            )
            rows = cursor.fetchall()
            cursor.close()

            # Build result dictionary
            result = {}
            for row in rows:
                entry = catalog_entry_utils.from_db_row(row)
                result[entry.dbid] = entry

            return result

    def put_catalog_entries(self, station_name, catalog_entries):
        """
        Put catalog entries
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            for entry in catalog_entries:
                if isinstance(entry, CatalogEntry):
                    # Convert hints list to JSON string for storage
                    hints = []
                    for hint in entry.hints:
                        hint_json = json.dumps(hint.to_json()) if entry.hints else None
                        hints.append(hint_json)
                    hints_json = json.dumps(hints) if hints else None

                    # Use INSERT OR REPLACE to overwrite existing entries

                    cursor.execute(
                        """INSERT OR REPLACE INTO catalog_entries
                                    (station, path, realpath, title, duration, tag, count, hints, content_type, media_type, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (
                            station_name,
                            entry.path,
                            entry.realpath,
                            entry.title,
                            entry.duration,
                            entry.tag,
                            entry.count,
                            hints_json,
                            entry.content_type,
                            entry.media_type,
                        ),
                    )

                else:
                    _logger.warning('Warning: Entry {} is not a CatalogEntry instance. Skipping.'.format(entry))

            connection.commit()
            cursor.close()

    def get_catalog_entries(self, station_name):
        """
        Get catalog entries
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """SELECT * 
                    FROM catalog_entries 
                    WHERE station = ?
                    ORDER BY tag, title""",
                (station_name, ),
            )

            rows = cursor.fetchall()
            cursor.close()

            catalog_entries = []
            for row in rows:
                # Create CatalogEntry object
                entry = catalog_entry_utils.from_db_row(row)
                catalog_entries.append(entry)

            return catalog_entries

    def search_catalog_entries(self, station_name, query):
        """
        Search catalog entries
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT * FROM catalog_entries 
                              WHERE station = ? AND (title LIKE ? OR tag LIKE ? OR path LIKE ?)
                              ORDER BY tag, title""",
                (station_name, '%{}%'.format(query), '%{}%'.format(query), '%{}%'.format(query)),
            )
            rows = cursor.fetchall()
            cursor.close()

            catalog_entries = []
            for row in rows:
                catalog_entries.append(catalog_entry_utils.from_db_row(row))

            return catalog_entries

    def delete_all_entries_for_station(self, station_name):
        """
        Delete all entries for station
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""DELETE FROM catalog_entries WHERE station = ?""", (station_name, ))
            connection.commit()
            cursor.close()

    def get_entry_by_path(self, station_name, path):
        """
        Get entry by path
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT * FROM catalog_entries 
                              WHERE station = ? AND path = ?""",
                (station_name, path),
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                # (_id, station, path, title, duration, tag, count, hints_str, created_at, updated_at) = row
                return catalog_entry_utils.from_db_row(row)

            return None

    def get_by_tag(self, station_name, tag):
        """
        Get by tag
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT * FROM catalog_entries 
                              WHERE station = ? AND tag = ?""",
                (station_name, tag),
            )
            rows = cursor.fetchall()
            cursor.close()

            catalog_entries = []
            for row in rows:
                catalog_entries.append(catalog_entry_utils.from_db_row(row))

            return catalog_entries

    def update_entry_count(self, station_name, path, new_count):
        """
        Update entry count
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """UPDATE catalog_entries 
                              SET count = ?, updated_at = CURRENT_TIMESTAMP 
                              WHERE station = ? AND path = ?""",
                (new_count, station_name, path),
            )
            connection.commit()
            cursor.close()

    # make a function to batch increment counts for multiple entries
    def batch_increment_counts(self, station_name, entries):
        """
        Batch increment counts
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            for entry in entries:
                if isinstance(entry, CatalogEntry):
                    cursor.execute(
                        """UPDATE catalog_entries 
                                      SET count = count + 1, updated_at = CURRENT_TIMESTAMP 
                                      WHERE station = ? AND path = ?""",
                        (station_name, entry.path),
                    )
                else:
                    _logger.warning('Warning: Entry {} is not a CatalogEntry instance. Skipping.'.format(entry))
            connection.commit()
            cursor.close()

    def find_best_candidates(self, station_name, tag, max_duration):
        """
        Find best candidates
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT * FROM catalog_entries 
                   WHERE station = ? AND tag = ? AND duration <= ? AND duration >= 1
                   ORDER BY count ASC, title ASC""",
                (station_name, tag, max_duration),
            )
            rows = cursor.fetchall()
            cursor.close()

            catalog_entries = []
            for row in rows:
                catalog_entries.append(catalog_entry_utils.from_db_row(row))

            return catalog_entries
