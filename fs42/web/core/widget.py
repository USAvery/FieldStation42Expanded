#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Render configurable widgets with isolated defaults and blueprint-local assets.
"""
import re
import os
import pkgutil
import importlib

from jinja2 import pass_context
from markupsafe import Markup

from fs42.web.core import settings

ATTRIBUTE_NAME = re.compile(r'^[A-Za-z_:][A-Za-z0-9_:.-]*$')


def get_widgets(groups=('widgets', 'menu_widgets')):
    """
    Discover reusable widget packages alongside their templates and assets
    """
    names = []
    for group in groups:
        package = importlib.import_module('fs42.web.blueprints.' + group)
        for item in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name):
            if item.ispkg:
                if item.name in names:
                    raise ValueError('Widget names must be unique: {}'.format(item.name))
                names.append(item.name)
    return tuple(names)


def widget_group(name):
    """
    Identify the widget family that owns a named component
    """
    for group in ('widgets', 'menu_widgets'):
        if name in get_widgets(groups=(group,)):
            return group
    raise ValueError('Unknown widget: {}'.format(name))


def widget_directory(name):
    """
    Locate a widget's assets beside its package source
    """
    module = importlib.import_module('fs42.web.blueprints.' + widget_group(name) + '.' + name)
    return os.path.dirname(module.__file__)


def widget_config(request, name, overrides=None):
    """
    Merge instance overrides over application-owned defaults without mutation
    """
    if name not in get_widgets():
        raise ValueError('Unknown widget: {}'.format(name))
    defaults = request.app.state.web_settings.get(widget_group(name), {}).get(name, {}).get('config', {})
    config = settings.merge(defaults, overrides or {})
    if name == 'selector':
        config['attributes'].setdefault('name', config['attributes']['id'])
    return config


def render_attributes(attributes):
    """
    Render HTML attributes with validated names and escaped values
    """
    values = []
    for name, value in attributes.items():
        if not ATTRIBUTE_NAME.fullmatch(name) or name.lower().startswith('on'):
            raise ValueError('Invalid widget attribute: {}'.format(name))
        if value is None or value is False:
            continue
        values.append(Markup(name) if value is True else Markup('{}="{}"').format(name, value))
    return Markup(' ').join(values)


@pass_context
def include_widget(context, name, config=None, caller=None):
    """
    Render a widget with configuration and an optional Jinja caller block
    """
    values = widget_config(context['request'], name, config)
    template = context['request'].app.state.templates.env.get_template(name + '/widget.html')
    return Markup(template.render(widget=values, request=context['request'], caller=caller))


def setup(templates):
    """
    Register widget templates, defaults, and escaped attribute rendering
    """
    templates.env.globals.update(include_widget=include_widget, render_attributes=render_attributes)


def template_directories():
    """
    Locate widget templates independently of the working directory
    """
    return [os.path.join(widget_directory(name), 'templates') for name in get_widgets()]
