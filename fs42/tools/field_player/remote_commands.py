#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Exchange commands and status with the player through runtime files for the standalone remote,
returning channel and program information after a command.
"""
import os
import json
import time
import traceback

from fs42.core import logger as project_logger
from fs42.tools.field_player._constants import SOCKET_PATH
from fs42.tools.field_player._constants import STATUS_SOCKET_PATH

_logger = project_logger.setup('fs42.tools.field_player.remote_commands')


def read_status():
    """
    Read the player's channel, network, and title for the remote, using channel -1 on failure
    """
    try:
        with open(STATUS_SOCKET_PATH, 'r') as fifo:
            line = fifo.readline()
            status = json.loads(line)
            return {
                'channel': status.get('channel_number', -1),
                'name': status.get('network_name', ''),
                'title': status.get('title', ''),
            }
    except Exception as e:
        traceback.print_exc()
        return {'channel': -1, 'name': ''}


def write_command(message):
    """
    Takes a dictionary command
    """
    message = json.dumps(message) + "\n"
    _logger.info('{} {}'.format('Writing to FIFO:', message))

    if not os.path.exists(SOCKET_PATH):
        raise Exception('FIFO not found: {}'.format(SOCKET_PATH))
    with open(SOCKET_PATH, 'w') as fifo:
        fifo.write(message)
        fifo.flush()

    # Give the player a moment to update status
    time.sleep(.25)

    status = read_status()
    return status
