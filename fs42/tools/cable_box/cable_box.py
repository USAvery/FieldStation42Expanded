#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Run the Raspberry Pi cable-box controls and numeric display. Read keypad input, send player
commands, and display channel, clock, or temperature information.
"""
import os
import sys
import json
import time
import subprocess

# Uses adafruit circuitpython via Blink - install blinka first:
# https://learn.adafruit.com/circuitpython-on-raspberrypi-linux/installing-circuitpython-on-raspberry-pi
# pip3 install adafruit-circuitpython-matrixkeypad
import board
import digitalio
import adafruit_matrixkeypad

# also requires tm1673 library:
# pip3 install raspberrypi-tm1637
import tm1637

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.cable_box.main')


def get_temperature():
    """
    Read the Raspberry Pi temperature and return rounded degrees Fahrenheit
    """
    a = str(subprocess.check_output(['vcgencmd', 'measure_temp']))
    _logger.info('{} {}'.format('A is', a))
    b = a.split('=')[1]
    c = float(b.split("'")[0])
    # output in form: temp=49.4'C
    f = round((c * 1.8) + 32)
    return f
    # return c


class CableBox(object):
    """
    Read a physical keypad and show channel, clock, or temperature information on the LED display
    """

    def __init__(self, channel_socket='runtime/channel.socket', status_socket='runtime/play_status.socket',
                 press_socket='runtime/press.socket'):
        """
        Initialize GPIO keypad and LED hardware and load clock-display preferences

        :param channel_socket: (str) file used to send player channel commands
        :param status_socket:  (str) file containing player status JSON
        :param press_socket:   (str) file containing remote-entered channel digits
        """
        self.channel_socket = channel_socket
        self.status_socket = status_socket
        self.press_socket = press_socket

        self.tm = tm1637.TM1637(clk=17, dio=18)
        self.tm.brightness(0)
        self.tm.show('FS42')

        column_pins = [digitalio.DigitalInOut(x) for x in (board.D26, board.D20, board.D21)]
        row_pins = [digitalio.DigitalInOut(x) for x in (board.D5, board.D6, board.D13, board.D19)]

        # Define keypad layout
        keys = (('1', '2', '3'), ('4', '5', '6'), ('7', '8', '9'), ('down', '0', 'up'))

        self.keypad = adafruit_matrixkeypad.Matrix_Keypad(row_pins, column_pins, keys)
        self.last_stat = ''

        # mode to display and update temp
        self.temp_mode = False
        self.last_button_time = time.monotonic()

        self.show_time = True
        self.time_format = '%H:%M'
        try:
            with open('confs/main_config.json') as fp:
                config = json.load(fp)
                self.show_time = config.get('show_cable_box_time', True)
                self.time_format = config.get('time_format', '%H:%M')
        except Exception:
            pass

    def send_command(self, command, channel=-1):
        """
        Send a player command or handle reserved exit, shutdown, and temperature channels

        :param command: (str) player action such as up, down, or direct
        :param channel: (int) direct channel number; 99 exits, 98 halts, and 97 shows temperature
        """
        as_obj = {'command': command, 'channel': channel}
        as_str = json.dumps(as_obj)
        if command == 'direct' and channel == 99:
            # then we want to shut the player down
            os.system('pkill -SIGINT -f field_player.py')
            sys.exit(0)
        elif command == 'direct' and channel == 98:
            # then we want to shutdown and halt the system
            os.system('pkill -9 -f field_player.py')
            os.system('killall mpv')
            os.system('sudo halt')
            sys.exit(-1)

        elif command == 'direct' and channel == 97:
            # temp = get_temperature()
            # self.tm.show(f"{temp}*")
            self.temp_mode = True
        else:
            _logger.info('Sending command: {}'.format(as_str))
            with open(self.channel_socket, 'w') as fp:
                fp.write(as_str)

    def check_status(self):
        """
        Read and decode player status only when its file contents change
        """
        new_stat = None
        with open(self.status_socket) as fp:
            as_str = fp.read()

            if as_str != self.last_stat:
                _logger.info('Status changed: {}'.format(as_str))
                self.last_stat = as_str
                try:
                    new_stat = json.loads(as_str)
                except:
                    # assume that it was a partial read and try again next time
                    _logger.error('Error decoding status: {}'.format(as_str))
        return new_stat

    def check_press(self):
        """
        Consume remote-entered channel digits and return them only when less than two seconds old
        """
        try:
            with open(self.press_socket) as fp:
                as_str = fp.read().strip()
            if not as_str:
                return None
            data = json.loads(as_str)
            with open(self.press_socket, 'w') as fp:
                fp.write('')
            if time.time() - data['ts'] < 2.0:
                return data['digits']
        except Exception:
            pass
        return None

    def read_keys(self):
        """
        Return the pressed keypad key only when exactly one key is held
        """
        pressed = self.keypad.pressed_keys
        if len(pressed) == 1:
            return pressed[0]
        return None

    def event_loop(self):
        """
        Poll the keypad and status files while updating channel selection and the idle display
        """
        last_pressed = ''
        in_selection = False
        last_selection_tick = -1
        channel_num = 0
        tick_count = 0
        while True:
            key_pressed = self.read_keys()

            if key_pressed:
                self.temp_mode = False
                self.last_button_time = time.monotonic()
                self.tm.show('    ')
                last_selection_tick = time.monotonic()
                in_selection = True

                as_num = None
                _logger.info('{} {}'.format('Key pressed:', key_pressed))

                if key_pressed == 'up':
                    self.send_command('up')
                    channel_num += 1
                    self.tm.show('----')
                    in_selection = False
                elif key_pressed == 'down':
                    if channel_num > 0:
                        self.send_command('down')
                        channel_num -= 1
                        self.tm.show('----')
                    in_selection = False
                else:
                    try:
                        as_num = int(last_pressed + key_pressed)
                        last_pressed = key_pressed
                        self.tm.show('  {0:02d}'.format(as_num))
                    except Exception:
                        pass

                time.sleep(0.3)

            # see if we need to reset selection or apply it
            if in_selection:
                tick_diff = time.monotonic() - last_selection_tick
                if tick_diff > 1.5:
                    _logger.info('Applying selection CH{0:02d}'.format(as_num))
                    self.tm.show('CH{0:02d}'.format(as_num))
                    last_selection_tick = -1
                    in_selection = False
                    last_pressed = ''
                    channel_num = as_num
                    self.send_command('direct', channel_num)

            time.sleep(0.1)

            if not in_selection:
                remote_digits = self.check_press()
                if remote_digits:
                    self.last_button_time = time.monotonic()
                    self.tm.show('  {0:02d}'.format(int(remote_digits)))

            new_stat = self.check_status()
            if new_stat:
                self.temp_mode = False
                try:
                    new_channel_num = int(new_stat['channel_number'])
                    if new_channel_num != channel_num:
                        self.last_button_time = time.monotonic()
                        channel_num = new_channel_num
                    if channel_num >= 0:
                        self.tm.show('CH{0:02d}'.format(channel_num))
                        _logger.info('{} {}'.format('Set channel: ', channel_num))
                    else:
                        self.tm.show('FS42')
                except:
                    self.tm.show('FS42')

            elapsed_since_press = time.monotonic() - self.last_button_time
            if self.show_time and elapsed_since_press > 15 and not in_selection and (tick_count % 10) == 0:
                formatted = time.strftime(self.time_format, time.localtime())
                if ':' in formatted:
                    h, m = formatted.split(':', 1)
                    self.tm.numbers(int(h), int(m))
                else:
                    self.tm.show(formatted)
            elif self.temp_mode and (tick_count % 10) == 0:
                temp = get_temperature()
                self.tm.show('{}*'.format(temp))

            tick_count += 1


if __name__ == '__main__':
    cable_box = CableBox()
    cable_box.event_loop()
