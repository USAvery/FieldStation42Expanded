#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Load web defaults, optional file overrides, and application-specific settings.
"""
import os
import json
from copy import deepcopy

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'settings.json')
OVERRIDE_ENV_VAR = 'FS42_WEB_SETTINGS'


def merge(base, override):
    """
    Recursively merge dictionaries without modifying the supplied settings
    """
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load(server_conf=None, override_file=None):
    """
    Load defaults, an optional override file, and the server's web settings
    """
    with open(SETTINGS_FILE, encoding='utf8') as f_in:
        loaded = json.load(f_in)
    override_file = override_file or os.getenv(OVERRIDE_ENV_VAR)
    if override_file:
        with open(override_file, encoding='utf8') as f_in:
            loaded = merge(loaded, json.load(f_in))
    return merge(loaded, (server_conf or {}).get('web', {}))


def blueprint_key(module):
    """
    Return the blueprint's package name relative to the blueprint root
    """
    return module.__name__.split('fs42.web.blueprints.', 1)[1]


def prefix(module, config):
    """
    Get an optional URL prefix by qualified package name or short name
    """
    key = blueprint_key(module)
    prefixes = config.get('url_prefixes', {})
    value = prefixes.get(key, prefixes.get(key.rsplit('.', 1)[-1], ''))
    if not isinstance(value, str) or (value and not value.startswith('/')) or any(c in value for c in '{}?#'):
        raise ValueError('Invalid URL prefix for {}'.format(key))
    return value.rstrip('/')
