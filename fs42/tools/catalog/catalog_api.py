#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Provide catalog searches, summaries, entry updates, and play-count updates through the catalog
database layer.
"""
from fs42.tools.catalog.catalog_io import CatalogIO


def get_summary(station_config):
    """
    Return a station's catalog entry count and combined media duration in seconds
    """
    entries = CatalogIO().get_catalog_entries(station_config['network_name'])
    duration = sum(entry.duration for entry in entries if entry.duration)
    return {
        'network_name': station_config['network_name'],
        'entry_count': len(entries),
        'total_duration': duration
    }


def delete_catalog(station_config):
    """
    Delete every stored catalog entry belonging to the configured network
    """
    CatalogIO().delete_all_entries_for_station(station_config['network_name'])


def set_entries(station_config, entries):
    """
    Replace the configured network's entire stored catalog with the supplied entries
    """
    delete_catalog(station_config)
    CatalogIO().put_catalog_entries(station_config['network_name'], entries)


def search_entries(station_config, query):
    """
    Find station catalog entries whose title, tag, or path matches the SQL LIKE query
    """
    return CatalogIO().search_catalog_entries(station_config['network_name'], query)


def get_entries(station_config):
    """
    Return all catalog entries for the configured network, ordered by tag and title
    """
    return CatalogIO().get_catalog_entries(station_config['network_name'])


def get_by_tag(station_config, tag):
    """
    Return station catalog entries with an exact matching content tag
    """
    return CatalogIO().get_by_tag(station_config['network_name'], tag)


def get_by_path(station_config, path):
    """
    Return a station catalog entry with the exact media path, or None when absent
    """
    return CatalogIO().get_entry_by_path(station_config['network_name'], path)


def update_play_counts(station_config, entries):
    """
    Flatten one level of entry lists and increment their stored station play counts

    :param station_config: (dict) station settings identifying the network to update
    :param entries:        (list) catalog entries or lists of catalog entries to count as scheduled
    """
    # flatten the entries list
    flat = []
    for entry in entries:
        if isinstance(entry, list):
            flat.extend(entry)
        else:
            flat.append(entry)
    CatalogIO().batch_increment_counts(station_config['network_name'], flat)


def get_entry_by_id(entry_id):
    """
    Return a catalog entry by database ID, or None when no row matches
    """
    return CatalogIO().entry_by_id(entry_id)


def get_entries_by_ids(entry_ids):
    """
    Fetch catalog entries in one query and index found entries by database ID
    """
    return CatalogIO().entries_by_ids(entry_ids)


def find_best_candidates(station_config, tag, max_duration):
    """
    Find tagged station media that fits the time limit, ordered by least-used first

    :param station_config: (dict) station settings identifying the network to search
    :param tag:            (str) exact content tag to match
    :param max_duration:   (float) maximum allowed media duration in seconds
    :return:               (lst<CatalogEntry>) entries lasting at least one second, ordered by count then title
    """
    return CatalogIO().find_best_candidates(station_config['network_name'], tag, max_duration)
