#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build the standalone handheld remote application
"""
from fastapi import FastAPI

from fs42.web.core.setup import setup_page_assets
from fs42.web.blueprints.api.remote_control import router as api_router
from fs42.web.blueprints.tools.handheld_remote import router as page_router


def create_app():
    """
    Create the standalone remote with its existing URLs
    """
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(page_router)
    setup_page_assets(app, [('handheld_remote', [])], {})
    return app


# Provide the ASGI entry point for uvicorn.
app = create_app()
