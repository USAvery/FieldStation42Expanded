#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Render blueprint-local templates with page metadata and application navigation.
"""
import os

from fs42.web.core import settings


def render_page(request, module_name, **context):
    """
    Render a page using its blueprint package and shared template helpers

    :param request:     (Request) the current HTTP request
    :param module_name: (str)     the page module's name
    :return:            (Response) the rendered page
    """
    name = module_name.rsplit('.', 1)[-1]
    module = request.app.state.page_modules[name]
    group = settings.blueprint_key(module).split('.')[0]
    directory = os.path.join(os.path.dirname(module.__file__), 'static')
    styles = [file for file in (name + '.css', 'style.css')
              if os.path.isfile(os.path.join(directory, file))]
    values = dict(title=module.TITLE, description=getattr(module, 'DESCRIPTION', ''),
                  page_name=name, page_group=group, page_styles=styles,
                  shared_utils=getattr(module, 'SHARED_UTILS', True),
                  navigation=request.app.state.page_navigation,
                  heading=getattr(module, 'HEADING', module.TITLE))
    values.update(context)
    return request.app.state.templates.TemplateResponse(request=request, name=name + '/index.html',
                                                        context=values)
