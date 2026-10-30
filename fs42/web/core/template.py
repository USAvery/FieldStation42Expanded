#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Register blueprint-aware URL helpers for Jinja templates.
"""
import hashlib
from functools import lru_cache

from jinja2 import pass_context
from starlette.routing import NoMatchFound
from starlette.staticfiles import StaticFiles
from fs42.web.core import routes
from fs42.web.core import widget
from fs42.core.controls import control_manifest


@pass_context
def sub_url_for(context, page, endpoint='index', **values):
    """
    Build a URL for a named view within a page blueprint
    """
    try:
        return context['request'].url_for(page + '.' + endpoint, **values).path
    except NoMatchFound:
        return '#'


@pass_context
def sub_static(context, page, filename):
    """
    Build an asset URL for a page blueprint
    """
    try:
        return static_url(context, page + '.static', path=filename)
    except NoMatchFound:
        return '#'


@lru_cache(maxsize=512)
def _asset_digest(filename, modified, changed, size):
    """Reuse a content fingerprint until the file's metadata changes."""
    with open(filename, 'rb') as asset:
        return hashlib.sha256(asset.read()).hexdigest()[:16]


@pass_context
def static_url(context, endpoint, **values):
    """Keep HTML and cached scripts/styles on the same version, including mounted paths."""
    request = context['request']
    url = request.url_for(endpoint, **values).path
    mount = next((route for route in request.app.routes if getattr(route, 'name', None) == endpoint), None)
    if mount is not None and isinstance(getattr(mount, 'app', None), StaticFiles):
        filename, stat = mount.app.lookup_path(values.get('path', '').lstrip('/'))
        if stat is not None:
            version = _asset_digest(filename, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
            return url + '?v=' + version
    return url


def setup(templates):
    """
    Register shared helpers in the application's Jinja environment
    """
    templates.env.globals.update(sub_url_for=sub_url_for, sub_static=sub_static, static_url=static_url,
                                 browser_config=routes.browser_config, control_manifest=control_manifest)
    widget.setup(templates)
