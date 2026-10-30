#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Register blueprint-aware URL helpers for Jinja templates.
"""
from jinja2 import pass_context
from starlette.routing import NoMatchFound
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
    return sub_url_for(context, page, 'static', path=filename)


def setup(templates):
    """
    Register shared helpers in the application's Jinja environment
    """
    templates.env.globals.update(sub_url_for=sub_url_for, sub_static=sub_static,
                                 browser_config=routes.browser_config, control_manifest=control_manifest)
    widget.setup(templates)
