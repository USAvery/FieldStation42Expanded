#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Register console API and page routers, shared scripts, template loaders, and static asset mounts for
the web applications.
"""
import os

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fs42.core import logger
from fs42.web.core import _pages
from fs42.web.core import routes
from fs42.web.core import errors
from fs42.web.core import settings
from fs42.web.core import widget
from fs42.web.core import template as tu
from fs42.web.core import _constants

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
    configure(app, conf)
    app.add_api_route('/favicon.ico', get_favicon, methods=['GET'], include_in_schema=False)
    app.add_api_route('/static/common.js', get_general_script, methods=['GET'], include_in_schema=False)
    app.add_api_route('/static/fs42_client.js', get_routing_script, methods=['GET'], include_in_schema=False)
    config = app.state.web_settings
    for module in _pages.get_pages(groups=('api',), config=config):
        routes.register_router(app, module)
    setup_pages(app, _pages.get_pages(config=config), conf)
    follow_symlink = conf.get('follow_static_symlinks', False)
    app.mount('/static', StaticFiles(directory=_constants.STATIC_DIR, html=True, follow_symlink=follow_symlink),
              name='static')
    app.state.browser_paths['/static/{path}'] = '/static/{path}'
    os.makedirs(_constants.GUIDE_VIDEO_DIR, exist_ok=True)
    app.mount('/guide_videos', StaticFiles(directory=_constants.GUIDE_VIDEO_DIR, follow_symlink=follow_symlink),
              name='guide_videos')
    app.state.browser_paths['/guide_videos/{path}'] = '/guide_videos/{path}'


def configure(app, conf):
    """
    Configure shared routing, settings, and errors for either web application
    """
    routes.initialize(app, settings.load(conf))
    errors.setup(app)


def setup_pages(app, pages, conf):
    """
    Register discovered page routers, navigation, templates, and static assets
    """
    # Mount static files with the operator's explicit symlink setting
    follow_symlink = conf.get('follow_static_symlinks', False)
    if follow_symlink:
        _logger.warning('Static symlinks are enabled; linked files outside the asset directories can be served')
    template_dirs = [os.path.join(_constants.WEB_DIR, 'templates')] + widget.template_directories()
    app.state.page_modules = {}
    app.state.page_navigation = []
    for module in pages:
        group = settings.blueprint_key(module).split('.')[0]
        page = module.__name__.rsplit('.', 1)[-1]
        if page in app.state.page_modules:
            raise ValueError('Page blueprint names must be unique: {}'.format(page))
        directory = os.path.dirname(module.__file__)
        routes.register_router(app, module)
        app.state.page_modules[page] = module
        if not getattr(module, 'HIDE_FROM_MENU', False):
            app.state.page_navigation.append(dict(
                name=page, title=getattr(module, 'MENU_TITLE', module.TITLE),
                group=getattr(module, 'MENU_GROUP', 'Console'),
                order=getattr(module, 'MENU_ORDER', 0),
                requires_player=getattr(module, 'REQUIRES_PLAYER', False)))
        template_dirs.append(os.path.join(directory, 'templates'))
        aliases = ['/static/tools/' + page] + getattr(module, 'STATIC_ALIASES', [])
        prefix = settings.prefix(module, app.state.web_settings)
        for index, url in enumerate(['/static/' + group + '/' + page] + aliases):
            app.mount(prefix + url, StaticFiles(directory=os.path.join(directory, 'static'), follow_symlink=follow_symlink),
                      name=page + '.static' if index == 0 else page + url)
            app.state.browser_paths[url + '/{path}'] = prefix + url + '/{path}'
    app.state.page_navigation.sort(key=lambda item: (item['group'], item['order'], item['title']))
    app.state.widget_sources = []
    for name in widget.get_widgets():
        group = widget.widget_group(name)
        directory = os.path.join(widget.widget_directory(name), 'static')
        if not os.path.isdir(directory):
            continue
        url = '/static/' + group + '/' + name
        app.mount(url, StaticFiles(directory=directory), name=group + '.' + name + '.static')
        for filename in sorted(os.listdir(directory)):
            if filename.endswith(('.js', '.css')):
                app.state.widget_sources.append(dict(group=group, name=name, filename=filename,
                                                     css=filename.endswith('.css')))
        app.state.browser_paths[url + '/{path}'] = url + '/{path}'
    app.state.templates = Jinja2Templates(directory=template_dirs)
    tu.setup(app.state.templates)
