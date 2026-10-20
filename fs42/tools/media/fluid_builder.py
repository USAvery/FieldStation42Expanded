#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage fluid builder
"""
import os
import sys
import logging
import sqlite3

sys.path.append(os.getcwd())

from fs42.tools.media import media_processor
from fs42.tools.media import fluid_statements
from fs42.core.station_manager import StationManager


class FluidBuilder(object):
    """
    FluidBuilder
    """

    def __init__(self, db_path=None):
        """
        Initialize the instance
        """
        if db_path is None:
            self.db_path = StationManager().server_conf['db_path']

        self._l = logging.getLogger('FLUID')
        connection = sqlite3.connect(self.db_path)
        try:
            fluid_statements.init_db(connection)
            connection.commit()
        finally:
            connection.close()

    def scan_file_cache(self, content_dir, media_filter='video'):
        """
        Scan file cache
        """
        connection = sqlite3.connect(self.db_path)
        try:
            # read all the files in the content dir
            self._l.info('Fluid file cache scan - reading {0} with media_filter={1}'.format(
                content_dir, media_filter))
            file_list = media_processor.rich_find_media(content_dir, media_filter)
            self._l.info('Comparing cache against {} files'.format(len(file_list)))
            # add any that aren't there yet
            fluid_statements.iterate_file_entries(connection, file_list)
            self._l.info('Checking file meta for stale entries.')
        finally:
            connection.close()

    def check_file_cache(self, full_path):
        """
        Check file cache
        """
        connection = sqlite3.connect(self.db_path)
        try:
            results = fluid_statements.check_file_cache(connection, full_path)
        finally:
            connection.close()
        return results

    def trim_file_cache(self, from_time):
        """
        Trim file cache
        """
        connection = sqlite3.connect(self.db_path)
        try:
            self._l.info('Trimming fluid file cache')
            fluid_statements.trim_file_entries(connection, from_time)
        finally:
            connection.close()

    def scan_breaks(self, dir_path):
        """
        Scan breaks
        """
        connection = sqlite3.connect(self.db_path)
        try:
            self._l.info('Scanning directory {} for breaks'.format(dir_path))
            if not os.path.isdir(dir_path):
                raise FileNotFoundError('Directory does not exist {}'.format(dir_path))
            dir_path = os.path.realpath(dir_path)
            file_list = media_processor._rfind_media(dir_path)

            # Check the cache because we require the duration to prococess.
            file_paths = [os.path.realpath(file) for file in file_list]
            cached_files = {}
            for path in file_paths:
                cached = fluid_statements.check_file_cache(connection, path)
                if cached:
                    cached_files[path] = cached

            for file in file_list:
                rfp = os.path.realpath(file)
                if rfp in cached_files:
                    cached = cached_files[rfp]
                    if fluid_statements.get_break_points(connection, rfp):
                        self._l.info('Breaks already exists for {}'.format(rfp))
                    else:
                        breaks = media_processor.black_detect(rfp, cached.duration)
                        fluid_statements.add_break_points(connection, rfp, breaks)
                else:
                    self._l.warning('{} is not in catalog cache - not adding break points.'.format(rfp))
            connection.commit()
        finally:
            connection.close()

    def get_breaks(self, full_path):
        """
        Get breaks
        """
        #fname = os.path.realpath(fname)
        connection = sqlite3.connect(self.db_path)
        try:
            results = fluid_statements.get_break_points(connection, full_path)
        finally:
            connection.close()
        return results

    def scan_chapters(self, dir_path):
        """
        Scan chapters
        """
        connection = sqlite3.connect(self.db_path)
        try:
            self._l.info('Scanning directory {} for chapters'.format(dir_path))
            if not os.path.isdir(dir_path):
                raise FileNotFoundError('Directory does not exist {}'.format(dir_path))
            dir_path = os.path.realpath(dir_path)
            file_list = media_processor._rfind_media(dir_path)

            # Check the cache because we require the duration to process.
            file_paths = [os.path.realpath(file) for file in file_list]
            cached_files = {}
            for path in file_paths:
                cached = fluid_statements.check_file_cache(connection, path)
                if cached:
                    cached_files[path] = cached

            for file in file_list:
                rfp = os.path.realpath(file)
                if rfp in cached_files:
                    cached = cached_files[rfp]
                    if fluid_statements.get_chapter_points(connection, rfp):
                        self._l.info('Chapters already exist for {}'.format(rfp))
                    else:
                        chapters = media_processor.chapter_detect(rfp, cached.duration)
                        if chapters:
                            fluid_statements.add_chapter_points(connection, rfp, chapters)
                        else:
                            self._l.info('No chapters found in {}'.format(rfp))
                else:
                    self._l.warning('{} is not in catalog cache - not adding chapter points.'.format(rfp))
            connection.commit()
        finally:
            connection.close()

    def get_chapters(self, full_path):
        """
        Get chapters
        """
        connection = sqlite3.connect(self.db_path)
        try:
            results = fluid_statements.get_chapter_points(connection, full_path)
        finally:
            connection.close()
        return results

    def scan_chapters_for_entries(self, entries):
        """
        Scan chapter markers for a list of catalog entries that don't have them yet
        """
        connection = sqlite3.connect(self.db_path)
        try:
            cursor = connection.cursor()
            for entry in entries:
                if hasattr(entry, 'realpath') and entry.realpath:
                    # Check if we've already scanned this file (row exists in table)
                    cursor.execute('SELECT path FROM chapter_points WHERE path=?', (entry.realpath, ))
                    if not cursor.fetchone():  # Never scanned before
                        # Scan for chapters
                        chapters = media_processor.chapter_detect(entry.realpath, entry.duration)
                        # Always store result, even if empty or None
                        fluid_statements.add_chapter_points(connection, entry.realpath,
                                                            chapters if chapters else [])
                        if chapters:
                            self._l.info('Added {0} chapters for {1}'.format(len(chapters), entry.realpath))
            cursor.close()
            connection.commit()
        finally:
            connection.close()


if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)s:%(name)s:%(message)s', level=logging.INFO)
    builder = FluidBuilder()
    # builder.scan_file_cache("catalog/nbc_content/")
    # exists = builder.check_file_cache("FieldStation42/catalog/public_domain/bextra/post-black.mov")
    builder.scan_breaks('catalog/public_domain/feature/sub/a/')
