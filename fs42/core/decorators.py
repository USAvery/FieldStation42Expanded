#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Wrap tool operations with exception logging while preserving the original exception and traceback.
"""
import functools

from fs42.core import logger


def error(subject):
    """
    Create a decorator that logs an operation's exception before re-raising it

    :param subject: (str) logger name used to report failures
    :return:        (callable) decorator preserving the wrapped function's metadata
    """

    def decorate(function):
        """
        Wrap a function with exception logging under the configured subject
        """

        @functools.wraps(function)
        def run(*args, **kwargs):
            """
            Call the wrapped operation and log any exception without suppressing it
            """
            try:
                return function(*args, **kwargs)
            except Exception:
                logger.setup(subject).exception('Could not complete {}'.format(subject))
                raise

        return run

    return decorate
