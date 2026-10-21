#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Represent a cached media-file record and convert between database rows and file-stat comparisons
used to detect changes.
"""


class FileRepoEntry(object):
    """
    Hold cached file identity, duration, metadata, and filesystem change timestamps
    """

    def __init__(self, db_row=None):
        """
        Create an empty media-cache record or restore one from a database row

        :param db_row: (tuple) stored file_meta column values, or None for an empty record
        """
        if not db_row:
            self.path = None
            self.duration = 0.0
            self.size = 0
            self.first_added = None
            self.last_mod = None
            self.last_checked = None
            self.last_updates = None
            self.meta = ''
            self.media_type = 'video'
        else:
            self.from_db_row(db_row)

    def __str__(self):
        """
        Format the cached path, duration, file size, and modification time
        """
        return 'Path:{0}, Dur:{1}, Sz:{2}, Mod:{3}'.format(self.path, self.duration, self.size, self.last_mod)

    def __eq__(self, value):
        """
        Compare cache records by path, file size, and modification time
        """
        return self.to_stat_check() == value.to_stat_check()

    def from_db_row(self, row):
        """
        Restore cached file fields, defaulting legacy rows to video media
        """
        # Handle both old (8 columns) and new (9 columns with media_type) schemas
        if len(row) == 9:
            (
                self.path,
                self.duration,
                self.size,
                self.first_added,
                self.last_mod,
                self.last_checked,
                self.last_updates,
                self.meta,
                self.media_type,
            ) = row
        else:  # Old schema with 8 columns
            (
                self.path,
                self.duration,
                self.size,
                self.first_added,
                self.last_mod,
                self.last_checked,
                self.last_updates,
                self.meta,
            ) = row
            self.media_type = 'video'  # Default for backward compatibility

    def to_db_row(self):
        """
        Return the legacy eight-column cache record tuple without the media-type field
        """
        return (
            self.path,
            self.duration,
            self.size,
            self.first_added,
            self.last_mod,
            self.last_checked,
            self.last_updates,
            self.meta,
        )

    def to_stat_check(self):
        """
        Return the path, byte size, and modification time used to detect file changes
        """
        return (self.path, self.size, self.last_mod)
