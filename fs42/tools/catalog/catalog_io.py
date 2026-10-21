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
    Persist and query station media catalogs in the configured SQLite database
    """

    def __init__(self):
        """
        Select the configured catalog database and create or upgrade its table
        """
        self.db_path = StationManager().server_conf['db_path']
        self._l = logging.getLogger('CATIO')
        self._init_catalog_table()

    @contextmanager
    def _get_connection(self):
        """
        Yield a SQLite connection, commit successful work, and roll back exceptions

        Close the connection on every exit from the context manager.
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
        Create the catalog table and add missing columns required by newer media records
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
        Read one catalog row by database ID, returning None when it does not exist
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
        Read catalog rows in one query and map found database IDs to restored entries
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
        Insert or replace a station's media records, serializing scheduling hints

        :param station_name:    (str) network name owning the entries
        :param catalog_entries: (list) CatalogEntry instances to persist; other values are skipped
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
        Return all entries for a station ordered by tag and title
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
        Search a station's title, tag, and path columns with a substring SQL LIKE pattern

        :param station_name: (str) network name restricting the search
        :param query:        (str) search text; SQL LIKE wildcards remain active
        :return:             (lst<CatalogEntry>) matching entries ordered by tag and title
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
        Remove every catalog database row belonging to the specified network
        """
        with self._get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""DELETE FROM catalog_entries WHERE station = ?""", (station_name, ))
            connection.commit()
            cursor.close()

    def get_entry_by_path(self, station_name, path):
        """
        Read a station's first exact-path catalog match, or return None
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
        Read all catalog entries matching both the network name and content tag
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
        Replace the stored play count and update timestamp for a station's media path
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
        Increment stored counts for the supplied station media entries in one transaction

        :param station_name: (str) network name owning the catalog rows
        :param entries:      (list) CatalogEntry instances whose paths should each gain one count
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
        Read tagged media within a duration limit, prioritizing the least-used entries

        :param station_name: (str) network name restricting the query
        :param tag:          (str) exact content tag to match
        :param max_duration: (float) maximum playback length in seconds
        :return:             (lst<CatalogEntry>) entries of at least one second ordered by count then title
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
