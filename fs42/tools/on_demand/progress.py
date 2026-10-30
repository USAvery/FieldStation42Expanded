# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Store resumable positions separately from live-channel playback and catalog counts."""
import hashlib
import math
import os
import sqlite3
import time

from pydantic import BaseModel, ConfigDict

from fs42.core.station_manager import StationManager
from fs42.tools.on_demand._constants import MAX_RESUME_POSITIONS


class PlaybackOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    start_over: bool = False


class PlaybackHistory:
    def __init__(self, db_path=None):
        self.db_path = db_path or StationManager().server_conf['db_path']

    @staticmethod
    def media_key(file_path, youtube=False):
        identity = file_path if youtube else os.path.normcase(os.path.realpath(file_path))
        return ('youtube:' if youtube else 'local:') + hashlib.sha256(identity.encode()).hexdigest()

    def _connect(self):
        # A background catalog write must not stall the player's input loop.
        connection = sqlite3.connect(self.db_path, timeout=0.1)
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS on_demand_progress '
                               '(media_key TEXT PRIMARY KEY, position REAL NOT NULL, duration REAL NOT NULL, '
                               'updated_at INTEGER NOT NULL DEFAULT 0)')
            columns = {row[1] for row in connection.execute('PRAGMA table_info(on_demand_progress)')}
            if 'updated_at' not in columns:
                with connection:
                    # Recheck under the write lock in case another process migrated first.
                    connection.execute('BEGIN IMMEDIATE')
                    columns = {row[1] for row in connection.execute('PRAGMA table_info(on_demand_progress)')}
                    if 'updated_at' not in columns:
                        connection.execute('ALTER TABLE on_demand_progress ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0')
            connection.execute('CREATE INDEX IF NOT EXISTS on_demand_progress_recency ON on_demand_progress(updated_at DESC)')
            with connection:
                self._trim(connection)
        except Exception:
            connection.close()
            raise
        return connection

    @staticmethod
    def _trim(connection):
        connection.execute('DELETE FROM on_demand_progress WHERE media_key IN '
                           '(SELECT media_key FROM on_demand_progress '
                           'ORDER BY updated_at DESC, rowid DESC LIMIT -1 OFFSET ?)', (MAX_RESUME_POSITIONS,))

    def position(self, key):
        connection = self._connect()
        try:
            row = connection.execute('SELECT position FROM on_demand_progress WHERE media_key = ?', (key,)).fetchone()
            return row[0] if row and math.isfinite(row[0]) and row[0] > 0 else 0
        finally:
            connection.close()

    def save(self, key, position, duration, completed=False):
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (position, duration)):
            return
        connection = self._connect()
        try:
            with connection:
                if completed or position < 1 or (duration > 0 and position >= duration - 5):
                    connection.execute('DELETE FROM on_demand_progress WHERE media_key = ?', (key,))
                else:
                    connection.execute('INSERT INTO on_demand_progress (media_key, position, duration, updated_at) VALUES (?, ?, ?, ?) '
                                       'ON CONFLICT(media_key) DO UPDATE SET position=excluded.position, duration=excluded.duration, '
                                       'updated_at=excluded.updated_at',
                                       (key, position, max(0, duration), time.time_ns()))
                    self._trim(connection)
        finally:
            connection.close()
