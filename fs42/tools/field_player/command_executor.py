#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Run executable channels as subprocesses and translate completion or interruption into player
outcomes.
"""
import time
import shlex
import subprocess

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.field_player.command_executor')


class CommandExecutor(object):
    """
    Start, inspect, and terminate the subprocess used by an executable channel
    """

    def __init__(self, command_str):
        """
        Store a command string until the executable channel is started
        """
        self.command = command_str
        self.process = None

    def start(self):
        """
        Split the configured command into arguments and launch it without a shell
        """
        try:
            # Safely split command with spaces/quotes
            args = shlex.split(self.command)
            self.process = subprocess.Popen(args)
        except Exception as e:
            raise RuntimeError('Failed to start command: {}'.format(e))

    def stop(self):
        """
        Terminate the launched process, wait for its exit, and clear the process reference
        """
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

    def get_status(self):
        """
        Report whether the command is stopped, running, or completed
        """
        if self.process is None:
            return 'stopped'
        elif self.process.poll() is not None:
            return 'completed'
        else:
            return 'running'


def execute_command(channel_conf, input_check_fn):
    """
    Run an executable channel until its process finishes or player input interrupts it

    :param channel_conf:   (dict) executable_command and optional executable_shutdown settings
    :param input_check_fn: (callable) callback returning a pending player command
    :return:               (PlayerOutcome) interrupting command, or None if the process finishes normally
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
