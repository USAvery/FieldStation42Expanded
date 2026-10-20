#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose the package interface
"""
import os

from fastapi import APIRouter

from fs42.web.core import _constants
from fs42.core.station_manager import StationManager

router = APIRouter(prefix='/about')


def _is_servable(theme_dir, file):
    """
    Is servable
    """

    full_path = os.path.join(theme_dir, file)
    if not os.path.isfile(full_path):
        # broken symlink or a directory
        return False

    if StationManager().server_conf.get('follow_static_symlinks', False):
        return True

    # symlinks pointing outside of the static dir are rejected by the static mount
    static_dir = os.path.realpath(_constants.STATIC_DIR)
    return os.path.commonpath([os.path.realpath(full_path), static_dir]) == static_dir


@router.get('/themes')
async def get_themes():
    """
    Get list of available themes
    """
    theme_dir = os.path.join(_constants.STATIC_DIR, 'themes')
    themes = []
    try:
        for file in os.listdir(theme_dir):
            if file.endswith('.css') and _is_servable(theme_dir, file):
                name = file.replace('.css', '')
                # Create a user-friendly name from the filename
                display_name = name.replace('_', ' ').replace('default', '').strip()
                if not display_name:
                    display_name = 'Default'
                themes.append({'id': name, 'name': display_name.title(), 'path': '/static/themes/{}'.format(file)})
        return {'themes': sorted(themes, key=lambda x: x['name'])}
    except Exception as e:
        return {
            'themes': [{
                'id': 'default',
                'name': 'Default',
                'path': '/static/themes/default.css'
            }],
            'error': str(e)
        }
