#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Browse deduplicated catalog pages and resolve selections to active local media
"""
import os
import sqlite3
from contextlib import closing

from fs42.core.station_manager import StationManager
from fs42.tools.catalog.catalog_io import CatalogIO
from fs42.tools.on_demand import _utils
from fs42.tools.on_demand import _constants


class OnDemand(object):
    """
    Read bounded library pages without scanning folders or loading another media player
    """

    def __init__(self):
        """
        Resolve active stations and ensure the existing catalog schema is available
        """
        self._manager = StationManager()
        self._catalog = CatalogIO()
        self._stations = {station['network_name']: station for station in self._manager.stations
                          if station.get('_has_catalog')}

    def _connect(self):
        """
        Open a short-lived database connection with metadata classification helpers
        """
        connection = sqlite3.connect(self._catalog.db_path)
        connection.row_factory = sqlite3.Row
        connection.create_function('media_kind', 2, _utils.media_kind, deterministic=True)
        connection.create_function('kids_content', 2, _utils.kids_content, deterministic=True)
        return connection

    def get_menu(self):
        """
        Return available browsing categories and catalog-enabled channel choices
        """
        return {'categories': _constants.CATEGORIES,
                'channels': [{'id': name, 'title': name} for name in sorted(self._stations)]}

    def _query(self, connection, columns, filters, stations):
        """
        Join cached metadata when available and restrict results to active catalog stations
        """
        has_metadata = connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'file_meta'").fetchone()
        join = ('LEFT JOIN file_meta AS m ON m.path = COALESCE(NULLIF(c.realpath, \'\'), c.path)'
                if has_metadata else '')
        return _constants.CATALOG_QUERY.format(metadata='m.meta' if has_metadata else 'NULL', join=join,
                                               stations=','.join('?' for _ in stations),
                                               columns=columns, filters=filters)

    def _describe(self, row):
        """
        Build title and detail text from cached metadata without exposing filesystem paths
        """
        meta = _utils.read_metadata(row['meta'])
        title = meta.get('title') or row['title']
        show = meta.get('show_title') if row['kind'] == 'episode' else None
        if show:
            title = '{}: {}'.format(show, title)
        return {'id': row['id'], 'title': title, 'kind': row['kind'], 'network': row['station'],
                'duration': row['duration'], 'year': str(meta.get('year') or ''),
                'description': meta.get('plot') or 'No description available.',
                'season': meta.get('season'), 'episode': meta.get('episode')}

    def get_titles(self, category='all', query='', channel='', page=0):
        """
        Fetch one stable title page with optional category, search, and channel filters

        :param category: (str) menu category identifying a supported filter
        :param query:    (str) literal title or series search text
        :param channel:  (str) optional network name
        :param page:     (int) zero-based result page
        :return:         (dict) title summaries, result count, and pagination state
        """
        result = {'items': [], 'total': 0, 'page': page, 'page_size': _constants.PAGE_SIZE}
        if not self._stations:
            return result
        if channel and channel not in self._stations:
            return result
        filters = []
        stations = [channel] if channel else list(self._stations)
        parameters = list(stations)
        if category in _constants.CATEGORY_FILTERS:
            filters.append(_constants.CATEGORY_FILTERS[category])
        if query.strip():
            filters.append("(instr(lower(title), lower(?)) > 0 OR instr(lower(meta), lower(?)) > 0)")
            parameters.extend([query.strip(), query.strip()])
        suffix = ''.join(' AND {}'.format(value) for value in filters)
        with closing(self._connect()) as connection:
            count_query = self._query(connection, 'COUNT(*)', suffix, stations)
            result['total'] = connection.execute(count_query, parameters).fetchone()[0]
            order = 'title COLLATE NOCASE, id'
            if category == 'top':
                order = 'play_count DESC, title COLLATE NOCASE, id'
            elif category == 'recent':
                order = 'id DESC'
            sql = self._query(connection, '*', suffix, stations) + ' ORDER BY {} LIMIT ? OFFSET ?'.format(order)
            rows = connection.execute(sql, parameters + [_constants.PAGE_SIZE, page * _constants.PAGE_SIZE]).fetchall()
            result['items'] = [self._describe(row) for row in rows]
        return result

    def get_selection(self, entry_id):
        """
        Revalidate catalog membership and local availability before requesting playback

        :param entry_id: (int) catalog entry selected in the menu
        :return:         (dict) local filename, source station, and display title
        """
        entry = self._catalog.entry_by_id(entry_id)
        if (entry is None or entry.station not in self._stations or entry.content_type != 'feature'
                or entry.media_type != 'video' or not os.path.isfile(entry.path)):
            raise ValueError('This title is no longer available. Refresh the library and try again.')
        return {'file_path': entry.path, 'network_name': entry.station, 'title': entry.title}
