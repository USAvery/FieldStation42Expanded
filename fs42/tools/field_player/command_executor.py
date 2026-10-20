#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage command executor
"""
import time
import shlex
import subprocess

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.field_player.command_executor')


class CommandExecutor(object):
    """
    CommandExecutor
    """

    def __init__(self, command_str):
        """
        Initialize the instance
        """
        self.command = command_str
        self.process = None

    def start(self):
        """
        Start
        """
        try:
            # Safely split command with spaces/quotes
            args = shlex.split(self.command)
            self.process = subprocess.Popen(args)
        except Exception as e:
            raise RuntimeError('Failed to start command: {}'.format(e))

    def stop(self):
        """
        Stop
        """
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

    def get_status(self):
        """
        Get status
        """
        if self.process is None:
            return 'stopped'
        elif self.process.poll() is not None:
            return 'completed'
        else:
            return 'running'


def execute_command(channel_conf, input_check_fn):
    """
    Execute command
    """
    process = CommandExecutor(channel_conf['executable_command'])
    process.start()
    keep_going = True
    while keep_going:
        time.sleep(0.05)
        response = input_check_fn()
        if response:
            _logger.info('Executable got shutdown command')
            keep_going = False
            if 'executable_shutdown' in channel_conf:
                shutdown_process = CommandExecutor(channel_conf['executable_shutdown'])
                shutdown_process.start()
            else:
                process.stop()
            return response
        elif process.get_status() != 'running':
            _logger.info('Executable not running')
            keep_going = False
