#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage fluid statements
"""
import os
import json
import logging
import datetime

from fs42.tools.media import media_processor
from fs42.tools.media.fluid_objects import FileRepoEntry


def check_file_cache(connection, full_path):
    """
    Find full_path and return fullpath if its in the file cache
    """

    cursor = connection.cursor()
    cursor.execute('SELECT * FROM file_meta WHERE path = ?;', (full_path, ))
    row = cursor.fetchone()
    result = None
    if row:
        repo_entry = FileRepoEntry(row)
        result = repo_entry
    cursor.close()
    return result


def iterate_file_entries(connection, entries):
    """
    Takes a list of file entries, determines if they are cached and adds them if not
    """

    cursor = connection.cursor()
    for entry in entries:
        # see if there is an entry already
        cursor.execute('SELECT * FROM file_meta WHERE path = ?;', (entry.path, ))
        row = cursor.fetchone()
        if row:
            repo_entry = FileRepoEntry()
            repo_entry.from_db_row(row)

            # Check if we need to update this entry
            needs_update = False

            # Update if file stats changed
            if entry != repo_entry:
                needs_update = True

            # Also update if this is an audio file with empty metadata
            # (happens when catalog was built before mutagen was installed)
            if repo_entry.media_type == 'audio' and not repo_entry.meta:
                logging.getLogger('FLUID').info('Audio file missing metadata, will refresh: {}'.format(entry.path))
                needs_update = True

            if needs_update:
                update_file_entry(connection, entry)
            elif repo_entry.media_type != 'audio':
                refresh_video_meta(connection, repo_entry)

        else:

            add_file_entry(connection, entry)
    cursor.close()


def refresh_video_meta(connection, repo_entry):
    """
    Refresh video meta
    """

    metadata = media_processor.extract_metadata(repo_entry.path, 'video')
    new_meta = json.dumps(metadata) if metadata else ''

    if new_meta != (repo_entry.meta or ''):
        logging.getLogger('FLUID').info('NFO metadata changed, refreshing: {}'.format(repo_entry.path))
        cursor = connection.cursor()
        cursor.execute(
            'UPDATE file_meta SET meta=?, last_checked=? WHERE path=?',
            (new_meta, datetime.datetime.now(), repo_entry.path),
        )
        cursor.close()
        connection.commit()


def trim_file_entries(connection, older_than):
    """
    Checks all files in the cache to ensure still on disk and removes them if not
    """

    cursor = connection.cursor()
    cursor.execute('SELECT * FROM file_meta WHERE last_updated < ?;', (older_than, ))
    to_remove = []
    rows = cursor.fetchall()
    logging.getLogger('FLUID').info('Checking {} files on the filesystem'.format(len(rows)))
    for row in rows:
        repo_entry = FileRepoEntry()
        repo_entry.from_db_row(row)
        if not os.path.exists(repo_entry.path):
            logging.getLogger('FLUID').info('File not found on filesystem - will remove: {}'.format(repo_entry))
            to_remove.append(repo_entry.path)

    connection.execute('BEGIN TRANSACTION;')

    for p in to_remove:
        cursor.execute('DELETE from file_meta WHERE path=?', (p, ))

    cursor.close()
    connection.commit()


def update_file_entry(connection, entry):
    """
    An old entry has changed, get the new stats and update it
    """
    cursor = connection.cursor()
    now = datetime.datetime.now()

    processed = media_processor.process_one(entry.path, 'processing', [])
    if not processed:
        return False
    entry.duration = processed.duration

    # Extract metadata: ID3 tags for audio, NFO sidecar for video
    media_type = media_processor.get_media_type(entry.path)
    metadata = media_processor.extract_metadata(entry.path, media_type)
    entry.meta = json.dumps(metadata) if metadata else ''

    logging.getLogger('FLUID').info('Updating existing file entry: {}'.format(entry.path))

    update = """UPDATE file_meta SET duration=?, size=?, last_mod=?, last_updated=?, last_checked=?, meta=?, media_type=?
        WHERE path=?;
        """
    values = (entry.duration, entry.size, entry.last_mod, now, now, entry.meta, media_type, entry.path)
    cursor.execute(update, values)
    cursor.close()
    connection.commit()


def add_file_entry(connection, entry):
    """
    This file isn't in the cache - add it
    """
    cursor = connection.cursor()
    now = datetime.datetime.now()

    entry.first_added = now
    entry.last_checked = now
    entry.last_updates = now

    processed = media_processor.process_one(entry.path, 'processing', [])
    if not processed:
        return False

    entry.duration = processed.duration

    # Extract metadata: ID3 tags for audio, NFO sidecar for video
    media_type = media_processor.get_media_type(entry.path)
    metadata = media_processor.extract_metadata(entry.path, media_type)
    entry.meta = json.dumps(metadata) if metadata else ''

    logging.getLogger('FLUID').info('Caching new file entry: {}'.format(entry))

    # Note: to_db_row() should now include media_type column
    cursor.execute('INSERT INTO file_meta VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);', entry.to_db_row() + (media_type, ))
    cursor.close()
    connection.commit()


def add_break_points(connection, path, points):
    """
    Add or update the break points for this file
    """
    cursor = connection.cursor()
    now = datetime.datetime.now()
    json_points = json.dumps(points)
    cursor.execute('REPLACE INTO break_points VALUES(?, ?, ?)', (path, json_points, now))
    cursor.close()
    connection.commit()


def get_break_points(connection, path):
    """
    Get the break points for this file
    """
    cursor = connection.cursor()
    cursor.execute('SELECT points FROM break_points WHERE path=?', (path, ))
    row = cursor.fetchone()
    result = {}
    if row:
        result = json.loads(row[0])
    cursor.close()
    return result


def delete_break_points(connection, path):
    """
    Delete any break points for this file
    """
    cursor = connection.cursor()
    cursor.execute('DELETE FROM break_points WHERE path=?', (path, ))
    cursor.close()
    connection.commit()


def add_chapter_points(connection, path, points):
    """
    Add or update the chapter points for this file
    """
    cursor = connection.cursor()
    now = datetime.datetime.now()
    json_points = json.dumps(points)
    cursor.execute('REPLACE INTO chapter_points VALUES(?, ?, ?)', (path, json_points, now))
    cursor.close()
    connection.commit()


def get_chapter_points(connection, path):
    """
    Get the chapter points for this file. Returns {} if no chapters or never scanned
    """
    cursor = connection.cursor()
    cursor.execute('SELECT points FROM chapter_points WHERE path=?', (path, ))
    row = cursor.fetchone()
    result = {}
    if row:
        loaded = json.loads(row[0])
        # Return {} if empty list (file was scanned but has no chapters)
        # This way schedule build sees it as "no usable chapters"
        result = loaded if loaded else {}
    cursor.close()
    return result


def delete_chapter_points(connection, path):
    """
    Delete any chapter points for this file
    """
    cursor = connection.cursor()
    cursor.execute('DELETE FROM chapter_points WHERE path=?', (path, ))
    cursor.close()
    connection.commit()


def init_db(connection):
    """
    Init db
    """
    cursor = connection.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS file_meta (
                            path TEXT PRIMARY KEY,
                            duration REAL,
                            size INTEGER,
                            first_added TIMESTAMP,
                            last_mod TIMESTAMP,
                            last_checked TIMESTAMP,
                            last_updated TIMESTAMP,
                            meta TEXT
                            )
                            """)

    # Check if media_type column exists, add it if it doesn't
    cursor.execute('PRAGMA table_info(file_meta)')
    columns = [column[1] for column in cursor.fetchall()]

    if 'media_type' not in columns:
        logging.getLogger('FLUID').info('Adding media_type column to file_meta table')
        cursor.execute("ALTER TABLE file_meta ADD COLUMN media_type TEXT DEFAULT 'video'")
        connection.commit()
        logging.getLogger('FLUID').info('Added media_type column to file_meta table')

    cursor.execute("""CREATE TABLE IF NOT EXISTS break_points (
                            path TEXT REFERENCES file_meta(path) PRIMARY KEY,
                            points TEXT,
                            last_updated TIMESTAMP
                            )
                       """)

    cursor.execute("""CREATE TABLE IF NOT EXISTS chapter_points (
                            path TEXT REFERENCES file_meta(path) PRIMARY KEY,
                            points TEXT,
                            last_updated TIMESTAMP
                            )
                       """)

    cursor.close()
