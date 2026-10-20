#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage decorators
"""
import functools

from fs42.core import logger


def error(subject):
    """
    Report an unhandled tool error and preserve its traceback
    """

    def decorate(function):
        """
        Decorate
        """

        @functools.wraps(function)
        def run(*args, **kwargs):
            """
            Run
            """
            try:
                return function(*args, **kwargs)
            except Exception:
                logger.setup(subject).exception('Could not complete {}'.format(subject))
                raise

        return run

    return decorate
