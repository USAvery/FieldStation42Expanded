#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Export registered browser endpoints and resolve legacy paths after URL-prefix overrides.
"""
from fastapi import Request
from fastapi.responses import JSONResponse

from fs42.web.core import settings


def register_router(app, module):
    """
    Register a router and retain its original-to-mounted path mapping
    """
    prefix = settings.prefix(module, app.state.web_settings)
    key = settings.blueprint_key(module)
    app.include_router(module.router, prefix=prefix)
    for route in module.router.routes:
        if not hasattr(route, 'path_format'):
            continue
        path = route.path_format
        name = route.name if key.startswith(('web_interface.', 'menu.')) else key + '.' + route.name
        app.state.browser_paths[path] = prefix + path
        if path != '/' and path.endswith('/'):
            app.state.browser_paths[path.rstrip('/')] = prefix + path
        app.state.browser_endpoints.setdefault(name, prefix + path)


def browser_config(request):
    """
    Build a request-local route map including the deployment's root path
    """
    prefix = request.scope.get('root_path', '').rstrip('/')
    return dict(root=prefix,
                paths={old: prefix + new for old, new in request.app.state.browser_paths.items()},
                endpoints={name: prefix + path for name, path in request.app.state.browser_endpoints.items()})


def initialize(app, config):
    """
    Initialize application-owned routing settings and the browser route endpoint
    """
    app.state.web_settings = config
    root_path = config.get('root_path', '')
    if not isinstance(root_path, str) or (root_path and not root_path.startswith('/')):
        raise ValueError('The web root_path must be empty or start with /')
    app.root_path = root_path.rstrip('/')
    app.state.browser_paths = {}
    app.state.browser_endpoints = {}
    app.add_api_route('/web/routes', get_routes, name='web.routes', include_in_schema=False)


def get_routes(request: Request):
    """
    Expose the same route map used by server-rendered pages
    """
    return JSONResponse(browser_config(request))
