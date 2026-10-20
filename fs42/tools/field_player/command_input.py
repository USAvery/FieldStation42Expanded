#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage command input
"""
import os
import sys
import json
import time
import datetime

import serial

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.field_player.command_input')

uart = serial.Serial('/dev/ttyAMA0', baudrate=9600, timeout=10)


def old_loop():
    """
    Old loop
    """
    while True:
        time.sleep(0.1)
        if uart.in_waiting > 0:
            message = uart.readline()
            command = message.decode('ascii')
            _logger.info('{} {}'.format('Got Message: ', command))
            if command.startswith('change'):
                timestamp = datetime.datetime.now()
                with open('runtime/channel.socket', 'w') as fp:
                    fp.write(str(timestamp))
            if command.startswith('exit'):
                os.system('pkill -9 -f field_player.py')
                os.system('killall mpv')
                sys.exit(-1)

            if command.startswith('halt'):
                os.system('pkill -9 -f field_player.py')
                os.system('killall mpv')
                os.system('sudo halt')
                sys.exit(-1)


def new_loop():
    """
    New loop
    """
    last_stat = ''
    while True:
        time.sleep(0.1)
        if uart.in_waiting > 0:
            try:
                message = uart.readline()
                command = message.decode('ascii')
                _logger.info('{} {}'.format('Got Message: ', command))
                as_json = json.loads(command)

                if as_json['channel'] == 99:
                    os.system('pkill -9 -f field_player.py')
                    os.system('killall mpv')
                    sys.exit(-1)
                elif as_json['channel'] == 98:
                    os.system('pkill -9 -f field_player.py')
                    os.system('killall mpv')
                    os.system('sudo halt')
                    sys.exit(-1)
                else:
                    with open('runtime/channel.socket', 'w') as fp:
                        fp.write(command)
            except Exception as e:
                _logger.error('Error decoding message')
                _logger.info(e)
        else:
            with open('runtime/play_status.socket') as fp:
                as_str = fp.read()

                if as_str != last_stat:
                    _logger.info('Status changed:')
                    last_stat = as_str
                    stat = json.loads(as_str)
                    uart.write('{}\n'.format(stat['channel_number']).encode('utf-8'))
                    # uart.flush()


if __name__ == '__main__':
    new_loop()
