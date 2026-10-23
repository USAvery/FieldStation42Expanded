#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Normalize cached metadata and classify local movies and episodes without probing media files
"""
import re
import json


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
    if meta.get('type') == 'episode' or re.search(r'(?i)(?:s\d{1,2}e\d{1,3}|\b\d{1,2}x\d{2}\b)', path):
        return 'episode'
    return 'movie'


def kids_content(value, tag):
    """
    Identify children's content from explicit genre and catalog tag labels
    """
    meta = read_metadata(value)
    text = '{} {}'.format(meta.get('genre', ''), tag).lower()
    return int(any(word in text for word in ('kids', 'children', 'family', 'animation', 'cartoon')))
