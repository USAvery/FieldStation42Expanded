#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage setup
"""
import os

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fs42.core import logger
from fs42.web.core import _pages
from fs42.web.core import _constants
from fs42.web.blueprints.api import routers
from fs42.web.blueprints.tools import routers as tool_routers

_logger = logger.setup('fs42.web.core.setup')


def get_favicon():
    """
    Serve the console icon
    """
    return FileResponse(os.path.join(_constants.STATIC_DIR, 'favicon.ico'))


def get_general_script():
    """
    Serve the shared utilities at their original asset URL
    """
    return FileResponse(os.path.join(_constants.STATIC_DIR, 'utils', 'general.js'))


def get_routing_script():
    """
    Serve the API client at its original asset URL
    """
    return FileResponse(os.path.join(_constants.STATIC_DIR, 'utils', 'routing.js'))


def setup(app, conf):
    """
    Register API routes and console assets
    """
    app.add_api_route('/favicon.ico', get_favicon, methods=['GET'], include_in_schema=False)
    app.add_api_route('/static/common.js', get_general_script, methods=['GET'], include_in_schema=False)
    app.add_api_route('/static/fs42_client.js', get_routing_script, methods=['GET'], include_in_schema=False)
    for router in routers:
        app.include_router(router)
    for router in tool_routers:
        app.include_router(router)

    setup_page_assets(app, _pages.PAGES, conf)
    follow_symlink = conf.get('follow_static_symlinks', False)
    app.mount('/static', StaticFiles(directory=_constants.STATIC_DIR, html=True, follow_symlink=follow_symlink),
              name='static')
    os.makedirs(_constants.GUIDE_VIDEO_DIR, exist_ok=True)
    app.mount('/guide_videos', StaticFiles(directory=_constants.GUIDE_VIDEO_DIR, follow_symlink=follow_symlink),
              name='guide_videos')


def setup_page_assets(app, pages, conf):
    """
    Register page templates and assets for a web application
    """
    # Mount static files with the operator's explicit symlink setting
    follow_symlink = conf.get('follow_static_symlinks', False)
    if follow_symlink:
        _logger.warning('Static symlinks are enabled; linked files outside the asset directories can be served')
    template_dirs = [os.path.join(_constants.WEB_DIR, 'templates')]
    for page, aliases in pages:
        directory = os.path.join(_constants.WEB_DIR, 'blueprints', 'tools', page)
        template_dirs.append(os.path.join(directory, 'templates'))
        for url in ['/static/tools/' + page] + aliases:
            app.mount(url, StaticFiles(directory=os.path.join(directory, 'static'), follow_symlink=follow_symlink),
                      name=page + url)
    app.state.templates = Jinja2Templates(directory=template_dirs)
