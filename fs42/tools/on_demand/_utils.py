#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Normalize cached metadata and classify local movies and episodes without probing media files
"""
import re
import json
import posixpath

from fs42.tools.on_demand import _constants


def read_metadata(value):
    """
    Decode cached metadata, tolerating missing or malformed records
    """
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def media_kind(value, path):
    """
    Prefer cached content types and recognize episode numbering when metadata is absent
    """
    meta = read_metadata(value)
    if meta.get('type') == 'episode' or re.search(_constants.EPISODE_NUMBER_PATTERN, path):
        return 'episode'
    return 'movie'


def media_show(value, path):
    """
    Prefer the cached series name, then use an episode filename or its show folder

    :param value: (str) cached metadata JSON
    :param path:  (str) catalog media path
    :return:      (str) series name used consistently for grouping and episode filters
    """
    meta = read_metadata(value)
    show = meta.get('show_title')
    if isinstance(show, str) and show.strip():
        return show.strip()
    path = path.replace('\\', '/')
    filename = posixpath.splitext(posixpath.basename(path))[0]
    number = re.search(_constants.EPISODE_NUMBER_PATTERN, filename)
    if number:
        title = filename[:number.start()].replace('.', ' ').replace('_', ' ').strip(' -')
        if title:
            return title
    folder = posixpath.dirname(path)
    if re.match(_constants.SEASON_FOLDER_PATTERN, posixpath.basename(folder)):
        folder = posixpath.dirname(folder)
    return posixpath.basename(folder) or 'Unknown Show'


def kids_content(value, tag):
    """
    Identify children's content from explicit genre and catalog tag labels
    """
    meta = read_metadata(value)
    text = '{} {}'.format(meta.get('genre', ''), tag).lower()
    return int(any(word in text for word in ('kids', 'children', 'family', 'animation', 'cartoon')))
