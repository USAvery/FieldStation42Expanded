#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Configure application logging and provide named loggers
"""
import logging


def setup(name):
    """
    Get the project logger for a module
    """
    return logging.getLogger(name)


def configure(verbose=False, logfile=None, rich=False):
    """
    Configure command-line diagnostics
    """
    handlers = []
    if rich:
        from rich.logging import RichHandler
        handlers.append(RichHandler())
    else:
        handlers.append(logging.StreamHandler())
    if logfile:
        handlers.append(logging.FileHandler(logfile))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format='[%(name)s] %(message)s',
                        handlers=handlers, force=True)
