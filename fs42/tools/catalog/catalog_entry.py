#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Represent cataloged media and convert entries to and from stored rows or JSON, including scheduling
hints and media-type information.
"""
import os
import json

from fs42.tools.schedule import schedule_hint
from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.catalog.catalog_entry')


def from_json_dict(json_data):
    """
    Reconstruct a catalog entry and its scheduling hints from serialized database fields

    :param json_data: (dict) stored entry fields, including station, dbid, and serialized hints
    :return:          (CatalogEntry) restored entry with defaults for legacy optional fields
    """
    # Create an entry from a JSON serializable dictionary
    tup = (
        json_data['dbid'],
        json_data['station'],
        json_data['path'],
        json_data['title'],
        json_data['duration'],
        json_data['tag'],
        json_data['count'],
        json_data['hints'],
        json_data.get('created_at', None),
        json_data.get('updated_at', None),
        json_data.get('realpath', None),
        json_data.get('content_type', 'feature'),
        json_data.get('media_type', 'video'),
    )
    return from_db_row(tup)


def from_db_row(row):
    """
    Reconstruct a catalog entry from a current or legacy SQLite row

    Default missing content and media types to feature and video. Restore recognized
    scheduling hints and log invalid or unknown hint data.

    :param row: (tuple) ordered catalog table values, including serialized hint JSON
    :return:    (CatalogEntry) restored media record and database metadata
    """

    if len(row) == 13:  # New schema with realpath, content_type, and media_type
        (dbid, station, path, title, duration, tag, count, hints_str, created, updated, realpath, content_type,
         media_type) = row
    elif len(row) == 12:  # Schema with realpath and content_type but no media_type
        (dbid, station, path, title, duration, tag, count, hints_str, created, updated, realpath,
         content_type) = row
        media_type = 'video'  # Default for backward compatibility
    elif len(row) == 11:  # Schema with realpath but no content_type or media_type
        (dbid, station, path, title, duration, tag, count, hints_str, created, updated, realpath) = row
        content_type = 'feature'  # Default for backward compatibility
        media_type = 'video'  # Default for backward compatibility
    else:  # Old schema without realpath
        (dbid, station, path, title, duration, tag, count, hints_str, created, updated) = row
        realpath = None
        content_type = 'feature'  # Default for backward compatibility
        media_type = 'video'  # Default for backward compatibility

    entry = CatalogEntry(path, duration, tag, None, count, content_type, media_type)
    entry.realpath = realpath
    entry.count = count
    entry.dbid = dbid
    entry.station = station
    entry.created_at = created
    entry.updated_at = updated

    hints = []
    # Load hints from JSON
    if hints_str:
        try:
            # Parse the JSON string back to list
            loaded_hints = json.loads(hints_str)

            if not isinstance(loaded_hints, list):
                loaded_hints = []

            for hint_str in loaded_hints:
                hint = json.loads(hint_str)
                # Convert each hint JSON back to its object
                if isinstance(hint, dict) and 'type' in hint:
                    klass = schedule_hint.HINT_KLASS_BY_TYPE.get(hint['type'])
                    if klass:
                        hints.append(schedule_hint.create_hint_from_json(klass, hint))
                    else:
                        _logger.warning('Warning: Unknown hint type {}. Skipping.'.format(hint['type']))
                else:
                    _logger.warning('Warning: Invalid hint format {}. Skipping.'.format(hint))
        except (json.JSONDecodeError, TypeError) as e:
            _logger.error(
                "Warning: Failed to decode hints from string '{}'. Using empty hints list.".format(hints_str))
            _logger.error('Error: {}'.format(e))
            hints = []

    entry.hints = hints
    return entry


class MatchingContentNotFound(Exception):
    pass


class NoFillerContentFound(Exception):
    pass


class CatalogEntry(object):
    """
    Represent cataloged media with its duration, selection tag, hints, and scheduling count
    """

    # CatalogEntry(row[2], row[3], float(row[4]), json.loads(row[6]) if row[6] else [])
    def __init__(self, path, duration, tag, hints=[], count=0, content_type='feature', media_type='video'):
        """
        Create a media record ready for catalog storage and schedule selection

        :param path:         (str) media filename or generated bump URL
        :param duration:     (float) playback length in seconds
        :param tag:          (str) content group used for schedule selection
        :param hints:        (list) scheduling constraints attached to this media
        :param count:        (int) number of recorded selections for scheduling
        :param content_type: (str) playback category such as feature, commercial, or bump
        :param media_type:   (str) media format category such as video or audio
        """
        self.path = path
        self.realpath = None
        # get the show name from the path
        self.title = os.path.splitext(os.path.basename(path))[0]
        self.duration = duration
        self.tag = tag
        self.count = count
        self.hints = hints
        self.content_type = content_type
        self.media_type = media_type
        self.station = None
        self.dbid = None
        self.created_at = None
        self.updated_at = None
        self.meta_cache = None

    def __str__(self):
        """
        Format the media title, tag, duration, scheduling hints, and path for a text listing
        """
        hints = list(map(str, self.hints))
        return '{0:<20.20} | {1:<10.10} | {2:<8.1f} | {3} | {4}'.format(self.title, self.tag, self.duration, hints,
                                                                        self.path)

    def to_json(self):
        """
        Return JSON-compatible catalog fields with serialized hints and ISO-format timestamps
        """
        # Convert the entry to a JSON serializable dictionary
        return {
            'dbid': self.dbid,
            'path': self.path,
            'title': self.title,
            'duration': self.duration,
            'tag': self.tag,
            'count': self.count,
            'content_type': self.content_type,
            'media_type': self.media_type,
            'hints': [hint.to_json() for hint in self.hints],  # Convert each hint to JSON
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
