#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage catalog api
"""
from fs42.tools.catalog.catalog_io import CatalogIO


def get_summary(station_config):
    """
    Get summary
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
    Delete catalog
    """
    CatalogIO().delete_all_entries_for_station(station_config['network_name'])


def set_entries(station_config, entries):
    """
    Set entries
    """
    delete_catalog(station_config)
    CatalogIO().put_catalog_entries(station_config['network_name'], entries)


def search_entries(station_config, query):
    """
    Search entries
    """
    return CatalogIO().search_catalog_entries(station_config['network_name'], query)


def get_entries(station_config):
    """
    Get entries
    """
    return CatalogIO().get_catalog_entries(station_config['network_name'])


def get_by_tag(station_config, tag):
    """
    Get by tag
    """
    return CatalogIO().get_by_tag(station_config['network_name'], tag)


def get_by_path(station_config, path):
    """
    Get by path
    """
    return CatalogIO().get_entry_by_path(station_config['network_name'], path)


def update_play_counts(station_config, entries):
    """
    Update play counts
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
    Get entry by id
    """
    return CatalogIO().entry_by_id(entry_id)


def get_entries_by_ids(entry_ids):
    """
    Batch lookup of catalog entries by IDs
    Returns a dictionary mapping entry_id -> CatalogEntry for found entries.
    """
    return CatalogIO().entries_by_ids(entry_ids)


def find_best_candidates(station_config, tag, max_duration):
    """
    Find best candidates
    """
    return CatalogIO().find_best_candidates(station_config['network_name'], tag, max_duration)
