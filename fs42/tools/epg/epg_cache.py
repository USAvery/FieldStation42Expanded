#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read cached XMLTV listings for configured streaming stations and expose their program times,
metadata, and coverage extents.
"""
import os
import sqlite3
import datetime

from fs42.tools.epg._constants import DEFAULT_DB_PATH


def _local_timestamp(value):
    """
    Convert a datetime or numeric timestamp to Unix seconds, treating naive dates as local time
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    if value.tzinfo is None:
        return int(value.astimezone().timestamp())

    return int(value.timestamp())


def _iso_local(timestamp):
    """
    Format Unix seconds as an ISO datetime using the current local timezone offset
    """
    return datetime.datetime.fromtimestamp(
        timestamp,
        tz=datetime.datetime.now().astimezone().tzinfo,
    ).isoformat()


def station_epg_config(station):
    """
    Return enabled EPG settings with a source and channel ID, or None if incomplete
    """
    config = station.get('epg')
    if not isinstance(config, dict):
        return None
    if config.get('enabled', True) is False:
        return None
    if not config.get('source') or not config.get('channel_id'):
        return None
    return config


def station_enabled(station):
    """
    Check whether a station has enabled, usable external program-guide settings
    """
    return station_epg_config(station) is not None


class EpgCache(object):
    """
    Read cached XMLTV listings without doing network or XML work
    """

    def __init__(self, db_path=DEFAULT_DB_PATH):
        """
        Select the existing XMLTV cache database to query

        :param db_path: (str) path to the cached listings database
        """
        self.db_path = os.fspath(db_path)

    def _connect(self):
        """
        Open the existing cache read-only, returning None if its file is absent
        """
        if not os.path.exists(self.db_path):
            return None

        uri = 'file:{}?mode=ro'.format(os.path.realpath(self.db_path))
        connection = sqlite3.connect(uri, uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only = ON')
        return connection

    def get_station_listings(
        self,
        station,
        start,
        end,
        include_meta=False,
    ):
        """
        Read cached programs overlapping a station's requested time window

        Apply the station's minute offset to cached times and return local ISO timestamps.
        Missing configuration, absent cache files, or query failures produce an empty list.

        :param station:      (dict) station settings containing source and XMLTV channel mappings
        :param start:        (datetime) start of the requested window, or Unix seconds
        :param end:          (datetime) end of the requested window, or Unix seconds
        :param include_meta: (bool) whether to include descriptions, episode titles, genres, and ratings
        :return:             (list) listing dictionaries ordered by broadcast start time
        """
        config = station_epg_config(station)
        if config is None:
            return []

        start_ts = _local_timestamp(start)
        end_ts = _local_timestamp(end)
        if start_ts is None or end_ts is None:
            return []

        offset_seconds = int(config.get('offset_minutes', 0) or 0) * 60
        query_start = start_ts - offset_seconds
        query_end = end_ts - offset_seconds

        connection = self._connect()
        if connection is None:
            return []

        try:
            rows = connection.execute(
                '''
                SELECT
                    start_ts,
                    end_ts,
                    title,
                    subtitle,
                    description,
                    category,
                    rating
                FROM programmes
                WHERE source = ?
                  AND channel_id = ?
                  AND start_ts < ?
                  AND end_ts > ?
                ORDER BY start_ts
                ''',
                (
                    config['source'],
                    config['channel_id'],
                    query_end,
                    query_start,
                ),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()

        listings = []

        for row in rows:
            listing = {
                'title': row['title'] or 'Programming',
                'start_time': _iso_local(row['start_ts'] + offset_seconds),
                'end_time': _iso_local(row['end_ts'] + offset_seconds),
            }

            if include_meta:
                meta = {}

                if row['description']:
                    meta['plot'] = row['description']

                if row['subtitle']:
                    meta['type'] = 'episode'
                    meta['title'] = row['subtitle']

                if row['category']:
                    meta['guide_category'] = row['category']
                    meta['genre'] = row['category']

                if row['rating']:
                    meta['rating'] = row['rating']

                if meta:
                    listing['meta'] = meta

            listings.append(listing)

        return listings

    def get_all_listings(
        self,
        stations,
        start,
        end,
        include_meta=False,
    ):
        """
        Collect cached listings for EPG-enabled stations, indexed by network name

        :param stations:     (list) station configuration dictionaries
        :param start:        (datetime) beginning of the requested window, or Unix seconds
        :param end:          (datetime) end of the requested window, or Unix seconds
        :param include_meta: (bool) whether to include program metadata
        :return:             (dict) network names mapped to their overlapping listings
        """
        schedules = {}

        for station in stations:
            if not station_enabled(station):
                continue

            schedules[station['network_name']] = self.get_station_listings(
                station,
                start,
                end,
                include_meta=include_meta,
            )

        return schedules

    def get_station_extents(self, station):
        """
        Find a station's earliest and latest cached times after applying its EPG offset

        :param station: (dict) station settings containing the EPG mapping
        :return:        (tuple) local ISO start and end times, or two None values if unavailable
        """
        config = station_epg_config(station)
        if config is None:
            return None, None

        connection = self._connect()
        if connection is None:
            return None, None

        try:
            row = connection.execute(
                '''
                SELECT MIN(start_ts) AS start_ts, MAX(end_ts) AS end_ts
                FROM programmes
                WHERE source = ? AND channel_id = ?
                ''',
                (config['source'], config['channel_id']),
            ).fetchone()
        except sqlite3.Error:
            return None, None
        finally:
            connection.close()

        if not row or row['start_ts'] is None or row['end_ts'] is None:
            return None, None

        offset_seconds = int(config.get('offset_minutes', 0) or 0) * 60

        return (
            _iso_local(row['start_ts'] + offset_seconds),
            _iso_local(row['end_ts'] + offset_seconds),
        )
