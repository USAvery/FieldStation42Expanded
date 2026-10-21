#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read cached media metadata in single or batch queries and normalize legacy fields into a consistent
representation for titles and displays.
"""
import os
import json
import logging
import sqlite3

_logger = logging.getLogger('MetadataIO')


def _default_db_path():
    """
    Read the metadata database filename from shared station settings
    """
    from fs42.core.station_manager import StationManager
    return StationManager().server_conf['db_path']


def pick_title(meta):
    """
    Prefer the series title for episodes and the regular title for other metadata
    """
    if not meta:
        return None
    if meta.get('type') == 'episode':
        return meta.get('show_title') or None
    return meta.get('title') or None


def normalize(meta):
    """
    Copy legacy metadata when needed to rename date to year and supply a missing music type
    """
    if not isinstance(meta, dict):
        return meta

    # Legacy audio rows stored the year under `date` and carried no type
    # discriminator. Bring them up to the normalized shape on read.
    needs_year = 'date' in meta and 'year' not in meta
    needs_type = 'type' not in meta
    if needs_year or needs_type:
        meta = dict(meta)
        if needs_year:
            meta['year'] = meta.pop('date')
        if needs_type:
            meta['type'] = 'music'
    return meta


def read_many(file_paths, db_path=None):
    """
    Read cached metadata in batches and map resolved files back to the caller's paths

    :param file_paths: (list) original media paths to look up
    :param db_path:    (str) optional database filename; None uses station settings
    :return:           (dict) original paths mapped to available normalized metadata
    """
    if not file_paths:
        return {}

    if db_path is None:
        try:
            db_path = _default_db_path()
        except Exception as e:
            _logger.warning('Could not resolve db_path for metadata read: {}'.format(e))
            return {}

    # Rows are keyed by realpath, so map back to what the caller asked for.
    # Several inputs can resolve to the same real file.
    by_real = {}
    for path in file_paths:
        try:
            real_path = os.path.realpath(os.path.abspath(path))
        except Exception:
            continue
        by_real.setdefault(real_path, []).append(path)

    results = {}
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            real_paths = list(by_real.keys())
            # Chunked to stay under SQLite's bound-variable limit
            chunk_size = 500
            for i in range(0, len(real_paths), chunk_size):
                chunk = real_paths[i:i + chunk_size]
                placeholders = ','.join('?' * len(chunk))
                cursor.execute('SELECT path, meta FROM file_meta WHERE path IN ({})'.format(placeholders), chunk)
                for real_path, meta_json in cursor.fetchall():
                    if not meta_json:
                        continue
                    meta = normalize(json.loads(meta_json))
                    for original in by_real.get(real_path, []):
                        results[original] = meta
            cursor.close()
    except Exception as e:
        _logger.warning('Could not batch read metadata: {}'.format(e))

    return results


def read(file_path, db_path=None):
    """
    Read normalized cached metadata for a media file's resolved absolute path

    :param file_path: (str) media filename whose metadata is requested
    :param db_path:   (str) optional database filename; None uses station settings
    :return:          (dict) decoded metadata, or None if absent or unreadable
    """
    if db_path is None:
        try:
            db_path = _default_db_path()
        except Exception as e:
            _logger.warning('Could not resolve db_path for metadata read: {}'.format(e))
            return None

    try:
        real_path = os.path.realpath(os.path.abspath(file_path))
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT meta FROM file_meta WHERE path = ?', (real_path, ))
            row = cursor.fetchone()
            cursor.close()

        if row and row[0]:
            return normalize(json.loads(row[0]))
    except Exception as e:
        _logger.warning('Could not read metadata for {0}: {1}'.format(file_path, e))

    return None
