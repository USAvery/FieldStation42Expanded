#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define playback argument errors and start the web API in a child process using the player's command
and shutdown queues.
"""


class FieldPlayerError(Exception):
    pass


def start_api_server(shutdown_queue, command_queue):
    """
    Start the web server in a child process
    """
    from fs42.web.app import run_with_shutdown_queue
    run_with_shutdown_queue(shutdown_queue, command_queue)
