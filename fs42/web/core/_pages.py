#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Discover router packages for the console and standalone remote applications.
"""
import pkgutil
import importlib

from fastapi import APIRouter


def get_pages(groups=('web_interface', 'menu'), standalone=False, config=None):
    """
    Find page packages for the requested application

    :param groups:     (tuple) blueprint groups to search
    :param standalone: (bool)  whether to load the standalone remote pages
    :return:           (list)  page modules with routers and page metadata
    """
    pages = []
    disabled = (config or {}).get('disabled_blueprints', [])

    def discover(package):
        for _, name, is_package in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name):
            key = package.__name__.split('fs42.web.blueprints.', 1)[1] + '.' + name
            if not is_package or any(key == item or key.startswith(item + '.') or name == item for item in disabled):
                continue
            module = importlib.import_module(package.__name__ + '.' + name)
            if not isinstance(getattr(module, 'router', None), APIRouter):
                discover(module)
                continue
            if not getattr(module, 'SHARED', False) and getattr(module, 'STANDALONE', False) != standalone:
                continue
            pages.append(module)
    for group in groups:
        if group not in disabled:
            discover(importlib.import_module('fs42.web.blueprints.' + group))
    return pages
