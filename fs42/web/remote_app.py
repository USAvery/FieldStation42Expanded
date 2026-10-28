#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build the standalone handheld remote application
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fs42.web.core import _pages
from fs42.web.core import setup
from fs42.web.core import routes
from fs42.web.core import _constants
from fs42.web.core.setup import setup_pages


def create_app(server_conf=None):
    """
    Create the standalone remote with its existing URLs
    """
    app = FastAPI()
    conf = server_conf or {}
    setup.configure(app, conf)
    config = app.state.web_settings
    for module in _pages.get_pages(groups=('api',), standalone=True, config=config):
        routes.register_router(app, module)
    setup_pages(app, _pages.get_pages(groups=('web_interface',), standalone=True, config=config), conf)
    app.mount('/static', StaticFiles(directory=_constants.STATIC_DIR), name='static')
    app.state.browser_paths['/static/{path}'] = '/static/{path}'
    return app


# Provide the ASGI entry point for uvicorn.
app = create_app()
