#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Translate Linux keyboard and IR input events into player API commands, guide navigation, PIN entry,
and service controls, with configurable mappings and input debouncing.
"""
import os
import sys
import json
import time
import argparse
import threading
import subprocess

import requests
from evdev import ecodes
from evdev import InputDevice

from fs42.core.controls import ACTIONS, KEY_ACTIONS
from fs42.tools.remote_control._constants import PRESS_SOCKET
from fs42.tools.remote_control._constants import DEBOUNCE_TIME
from fs42.tools.remote_control._constants import SETTINGS_FILE
from fs42.tools.remote_control._constants import USE_SYSTEMCTL
from fs42.tools.remote_control._constants import CALLBACK_MAP_FILE
from fs42.tools.remote_control._constants import SYSTEMCTL_TO_TOGGLE
from fs42.tools.remote_control._constants import DEFAULT_KEY_MAPPINGS

# ======================================
# CONFIGURATION - CUSTOMIZE YOUR MAPPINGS
# ======================================

# Server Configuration - can be overridden by environment variables
from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.remote_control.remote_control')

FS42_HOST = os.getenv('FS42_HOST', '127.0.0.1')
FS42_PORT = os.getenv('FS42_PORT', '4242')
FS42_BASE_URL = 'http://{0}:{1}'.format(FS42_HOST, FS42_PORT)
KEY_MAPPINGS = DEFAULT_KEY_MAPPINGS.copy()

if os.path.exists(SETTINGS_FILE):
    _logger.info('Loading settings from {}'.format(SETTINGS_FILE))
    try:
        with open(SETTINGS_FILE, 'r') as file:
            remote_settings = json.load(file)
        if remote_settings.get('use_systemctl') is not None:
            _logger.info('Loading USE_SYSTEMCTL from file')
            USE_SYSTEMCTL = bool(remote_settings['use_systemctl'])
        if remote_settings.get('systemctl_to_toggle') is not None:
            _logger.info('Loading SYSTEMCTL_TO_TOGGLE from file')
            SYSTEMCTL_TO_TOGGLE = remote_settings['systemctl_to_toggle']
        if remote_settings.get('key_mappings') is not None:
            _logger.info('Loading KEY_MAPPINGS from file')
            file_mappings = remote_settings['key_mappings']
            KEY_MAPPINGS = file_mappings.copy()
            for function, key in DEFAULT_KEY_MAPPINGS.items():
                if function not in KEY_MAPPINGS and key not in KEY_MAPPINGS.values():
                    KEY_MAPPINGS[function] = key
    except Exception as e:
        _logger.error('Error loading settings from file: {}'.format(e))

# Channel input state
channel_input = ''
channel_input_timer = None
input_lock = threading.Lock()

# Last channel tracking
current_channel = None
last_channel = None

# Custom interactive guide routing
_custom_guide_channel = None
_custom_guide_channel_checked = False

# Debounce tracking - stores last press time for each function
last_press_time = {}
debounce_lock = threading.Lock()


def get_custom_guide_channel():
    """
    Return the configured custom web guide channel number, if present
    """
    global _custom_guide_channel, _custom_guide_channel_checked

    if _custom_guide_channel_checked:
        return _custom_guide_channel

    _custom_guide_channel_checked = True
    try:
        from fs42.core.station_manager import StationManager
        guide = StationManager().guide_config
        if (guide and guide.get('network_type') == 'web'
                and 'static/customguide/customguide.html' in guide.get('web_url', '')):
            _custom_guide_channel = guide.get('channel_number')
    except Exception as e:
        _logger.warning('Unable to detect custom guide channel: {}'.format(e))

    return _custom_guide_channel


def custom_guide_is_active():
    """
    Check the actual player status so normal remote mappings resume after tuning away
    """
    try:
        response = requests.get('{}/player/status'.format(FS42_BASE_URL), timeout=1)
        if not response.ok:
            return False
        status = response.json()
        guide_channel = get_custom_guide_channel()
        return bool(status.get('guide_visible') or status.get('on_demand_playing')
                    or (guide_channel is not None and status.get('channel_number') == guide_channel))
    except Exception:
        return False


def post_control(action, arguments=None):
    """Use the same validated actions as the web remote, independent of page URLs."""
    arguments = arguments or {}
    ACTIONS[action].message(arguments)
    return requests.post(FS42_BASE_URL + '/controls/dispatch',
                         json={'action': action, 'arguments': arguments}, timeout=2)


def send_custom_guide_key(key_name):
    """Forward a key by action; the player determines which menu owns focus."""
    action = KEY_ACTIONS.get(key_name)
    if action is None:
        return False
    try:
        response = post_control(action)
        if response.ok:
            _logger.info('Custom guide key sent: {}'.format(key_name))
            return True
        _logger.error('Custom guide key failed: {0} ({1})'.format(key_name, response.status_code))
    except Exception as e:
        _logger.error('Custom guide key error: {}'.format(e))
    return False


def read_exec_mappings():
    """
    Read configured key-to-shell-command mappings, using an empty mapping if absent or invalid
    """
    mappings = {}
    if not os.path.exists(CALLBACK_MAP_FILE):
        return mappings
    with open(CALLBACK_MAP_FILE, 'r') as f:
        contents = f.read()
        try:
            mappings = json.loads(contents)
        except Exception as e:
            _logger.info(e)
            pass
        return mappings


exec_mappings = read_exec_mappings()


def write_press_socket(digits):
    """
    Publish the currently entered channel digits and their timestamp to the status file
    """
    try:
        with open(PRESS_SOCKET, 'w') as fp:
            json.dump({'digits': digits, 'ts': time.time()}, fp)
    except Exception as e:
        _logger.error('Failed to write press socket: {}'.format(e))


def clear_press_socket():
    """
    Empty the channel-digit status file after the pending entry is cleared
    """
    try:
        with open(PRESS_SOCKET, 'w') as fp:
            fp.write('')
    except Exception:
        pass


def should_allow_press(function_name, debounce_time=DEBOUNCE_TIME):
    """
    Check if enough time has passed since last press of this function
    """
    global last_press_time

    with debounce_lock:
        current_time = time.time()
        last_time = last_press_time.get(function_name, 0)

        if current_time - last_time >= debounce_time:
            last_press_time[function_name] = current_time
            return True
        else:
            return False


def send_channel_change():
    """
    Send accumulated channel input to the server
    """
    global channel_input, channel_input_timer, current_channel, last_channel

    with input_lock:
        if channel_input:
            try:
                channel_number = int(channel_input)
                _logger.info('Sending channel change to {}'.format(channel_number))
                response = post_control('channel.tune', {'channel': channel_number})
                if response.ok:
                    _logger.info('Changed to channel {}'.format(channel_number))
                    # Update channel tracking - only update last_channel if we know the current channel
                    if current_channel is not None and current_channel != channel_number:
                        last_channel = current_channel
                        _logger.info('Updated last_channel: {0} (was on {1}, now on {2})'.format(
                            last_channel, current_channel, channel_number))
                    current_channel = channel_number
                else:
                    _logger.error('Channel change to {} failed'.format(channel_number))
            except Exception as e:
                _logger.error('Channel change error: {}'.format(e))

            # Clear the input
            channel_input = ''
            channel_input_timer = None
            clear_press_socket()


def send_parental_digit_if_active(number):
    """
    Forward a numeric key to PIN entry when the player is awaiting parental authorization

    :param number: (int) digit entered on the remote
    :return:       (bool) whether the player accepted the digit as PIN input
    """
    try:
        status_response = requests.get('{}/player/status'.format(FS42_BASE_URL), timeout=2)
        if not status_response.ok:
            return False

        status = status_response.json()
        if not status.get('awaiting_pin'):
            return False

        response = post_control('parental.digit', {'digit': str(number)})

        if response.ok:
            _logger.info('Parental controls PIN digit entered: {}'.format(number))
            return True

        _logger.error('Parental controls digit failed: {}'.format(response.status_code))
        return False
    except Exception as e:
        _logger.error('Parental controls digit error: {}'.format(e))
        return False


def number_pressed(number):
    """
    Handle number key presses from remote
    """
    global channel_input, channel_input_timer

    if send_parental_digit_if_active(number):
        return

    with input_lock:
        # Cancel any existing timer
        if channel_input_timer:
            channel_input_timer.cancel()
            channel_input_timer = None

        # Add digit to input
        channel_input += str(number)
        _logger.info('Channel input: {}'.format(channel_input))
        write_press_socket(channel_input)

        # If we have 3 digits, send immediately
        if len(channel_input) >= 3:
            # Use a very short timer to avoid race conditions
            channel_input_timer = threading.Timer(0.1, send_channel_change)
            channel_input_timer.start()
        else:
            # Set timeout for 1 second
            channel_input_timer = threading.Timer(1.0, send_channel_change)
            channel_input_timer.start()


def show_guide_pressed():
    """
    Handle home key press
    """
    if not should_allow_press('show_guide'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    try:
        response = post_control('menu.guide')
        if response.ok:
            _logger.info('Guide displayed')
            if current_channel is not None:
                last_channel = current_channel
                _logger.info('Stored last_channel: {} before guide'.format(last_channel))
        else:
            _logger.error('Guide command failed')
    except Exception as e:
        _logger.error('Guide error: {}'.format(e))


def show_on_demand_pressed():
    """
    Open the On Demand menu from its dedicated, configurable remote button
    """
    if not should_allow_press('show_on_demand'):
        return
    try:
        response = post_control('menu.on_demand')
        response.raise_for_status()
    except requests.RequestException as error:
        _logger.error('On Demand command failed: {}'.format(error))


def volume_up_pressed():
    """
    Handle right arrow key press
    """
    if not should_allow_press('volume_up'):
        return  # Debounced - ignore this press

    try:
        response = post_control('volume.up')
        if response.ok:
            data = response.json()['result']
            _logger.info('Volume up: {}'.format(data.get('volume', 'success')))
        else:
            _logger.error('Volume up failed')
    except Exception as e:
        _logger.error('Volume up error: {}'.format(e))


def volume_down_pressed():
    """
    Handle left arrow key press
    """
    if not should_allow_press('volume_down'):
        return  # Debounced - ignore this press

    try:
        response = post_control('volume.down')
        if response.ok:
            data = response.json()['result']
            _logger.info('Volume down: {}'.format(data.get('volume', 'success')))
        else:
            _logger.error('Volume down failed')
    except Exception as e:
        _logger.error('Volume down error: {}'.format(e))


def mute_pressed():
    """
    Handle mute key press
    """
    if not should_allow_press('mute'):
        return  # Debounced - ignore this press

    try:
        response = post_control('volume.mute')
        if response.ok:
            data = response.json()['result']
            _logger.info('Mute toggled: {}'.format(data.get('volume', 'success')))
        else:
            _logger.error('Mute toggle failed')
    except Exception as e:
        _logger.error('Mute error: {}'.format(e))


def channel_up_pressed():
    """
    Handle up arrow key press
    """
    if not should_allow_press('channel_up'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    try:
        response = post_control('channel.next')
        if response.ok:
            _logger.info('Channel up success')
            # Poll status to wait for channel change (max 1 second)
            try:
                old_channel = current_channel
                new_channel = None
                max_attempts = 20  # 20 attempts * 0.05s = 1 second max

                for attempt in range(max_attempts):
                    time.sleep(0.05)
                    status_response = requests.get('{}/player/status'.format(FS42_BASE_URL))
                    if status_response.ok:
                        status = status_response.json()
                        new_channel = status.get('channel_number')

                        # If channel changed or we have a channel number, we're done
                        if new_channel != old_channel:
                            break

                _logger.info('DEBUG: Status returned channel_number={0}, current_channel={1}'.format(
                    new_channel, current_channel))
                # Only update last_channel if the channel actually changed
                if new_channel != current_channel and current_channel is not None:
                    last_channel = current_channel
                    _logger.info('Channel changed: {0} -> {1} (Last: {2})'.format(
                        current_channel, new_channel, last_channel))
                else:
                    _logger.info('Channel unchanged: new={0}, current={1}'.format(new_channel, current_channel))
                current_channel = new_channel
            except Exception as e:
                _logger.error('Failed to get current channel: {}'.format(e))
                current_channel = None
        else:
            _logger.error('Channel up failed')
    except Exception as e:
        _logger.error('Channel up error: {}'.format(e))


def channel_down_pressed():
    """
    Handle down arrow key press
    """
    if not should_allow_press('channel_down'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    try:
        response = post_control('channel.previous')
        if response.ok:
            _logger.info('Channel down success')
            # Poll status to wait for channel change (max 1 second)
            try:
                old_channel = current_channel
                new_channel = None
                max_attempts = 20  # 20 attempts * 0.05s = 1 second max

                for attempt in range(max_attempts):
                    time.sleep(0.05)
                    status_response = requests.get('{}/player/status'.format(FS42_BASE_URL))
                    if status_response.ok:
                        status = status_response.json()
                        new_channel = status.get('channel_number')

                        # If channel changed or we have a channel number, we're done
                        if new_channel != old_channel:
                            break

                _logger.info('DEBUG: Status returned channel_number={0}, current_channel={1}'.format(
                    new_channel, current_channel))
                # Only update last_channel if the channel actually changed
                if new_channel != current_channel and current_channel is not None:
                    last_channel = current_channel
                    _logger.info('Channel changed: {0} -> {1} (Last: {2})'.format(
                        current_channel, new_channel, last_channel))
                else:
                    _logger.info('Channel unchanged: new={0}, current={1}'.format(new_channel, current_channel))
                current_channel = new_channel
            except Exception as e:
                _logger.error('Failed to get current channel: {}'.format(e))
                current_channel = None
        else:
            _logger.error('Channel down failed')
    except Exception as e:
        _logger.error('Channel down error: {}'.format(e))


def last_channel_pressed():
    """
    Handle last channel key press
    """
    if not should_allow_press('last_channel'):
        return  # Debounced - ignore this press

    global current_channel, last_channel
    if last_channel is not None:
        try:
            _logger.info('Switching to last channel: {}'.format(last_channel))
            response = post_control('channel.tune', {'channel': last_channel})
            if response.ok:
                _logger.info('Switched to last channel {}'.format(last_channel))
                # Swap current and last channel
                temp = current_channel
                current_channel = last_channel
                last_channel = temp
            else:
                _logger.error('Last channel change to {} failed'.format(last_channel))
        except Exception as e:
            _logger.error('Last channel error: {}'.format(e))
    else:
        _logger.info('No last channel stored')


def end_pressed():
    """
    Handle end key press - stop the player
    """
    if not should_allow_press('power_stop'):
        return  # Debounced - ignore this press

    try:
        response = post_control('player.stop')
        if response.ok:
            _logger.info('Player stopped')
        else:
            _logger.error('Stop command failed')
    except Exception as e:
        _logger.error('Stop error: {}'.format(e))


def toggle_services():
    """
    Toggle FieldStation42 services on/off - true power button behavior
    """
    if not should_allow_press('power_stop'):
        return  # Debounced - ignore this press

    try:
        # Check if fs42.service is active to determine current state
        result = subprocess.run(['systemctl', '--user', 'is-active', 'fs42.service'], capture_output=True,
                                text=True, timeout=5)

        services_active = result.stdout.strip() == 'active'

        if services_active:
            # Services are running, stop them
            for service in SYSTEMCTL_TO_TOGGLE:
                try:
                    # Fire and forget - don't wait for completion since services may have delays
                    subprocess.Popen(['systemctl', '--user', 'stop', service], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    _logger.info('Stopping {}'.format(service))
                except Exception as e:
                    _logger.error('Error stopping {0}: {1}'.format(service, e))
        else:
            # Services are not running, start them
            for service in SYSTEMCTL_TO_TOGGLE:
                try:
                    # Fire and forget - don't wait for completion since services have startup delays
                    subprocess.Popen(['systemctl', '--user', 'start', service], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    _logger.info('Starting {}'.format(service))
                except Exception as e:
                    _logger.error('Error starting {0}: {1}'.format(service, e))

    except subprocess.TimeoutExpired:
        _logger.error('Error: systemctl command timed out')
    except Exception as e:
        _logger.error('Error toggling services: {}'.format(e))


def find_input_device(device_spec=None):
    """
    Find the Flirc or keyboard input device

    :param device_spec: (obj) Optional device specifier. Can be:
            - Device path (e.g., '/dev/input/event3')
            - Device index (e.g., '0', '1', '2')
            - Device name pattern (e.g., 'flirc', 'keyboard')
            - None to auto-detect
    """
    import glob
    devices = []
    default = False
    # Look for input devices
    for device_path in glob.glob('/dev/input/event*'):
        try:
            device = InputDevice(device_path)
            # Look for devices that can send key events
            if ecodes.EV_KEY in device.capabilities():
                devices.append((device_path, device.name))
        except (OSError, PermissionError):
            continue

    if not devices:
        _logger.info('No keyboard/remote devices found. Run with sudo?')
        return None

    _logger.info('Available input devices:')
    for i, (path, name) in enumerate(devices):
        _logger.info('{0}: {1} ({2})'.format(i, name, path))

    # If device_spec is provided, try to match it
    if device_spec:
        # Check if it's a direct device path
        if device_spec.startswith('/dev/input/'):
            if os.path.exists(device_spec):
                _logger.info('Using specified device path: {}'.format(device_spec))
                return device_spec
            else:
                _logger.warning(
                    "Warning: Device path '{}' not found, falling back to auto-detect".format(device_spec))

        # Check if it's a numeric index
        elif device_spec.isdigit():
            index = int(device_spec)
            if 0 <= index < len(devices):
                path, name = devices[index]
                _logger.info('Using device at index {0}: {1} ({2})'.format(index, name, path))
                return path
            else:
                _logger.warning(
                    'Warning: Device index {0} out of range (0-{1}), falling back to auto-detect'.format(
                        index,
                        len(devices) - 1))

        # Treat it as a name pattern
        else:
            device_spec = device_spec.lower()

    # If no spec provided, default to flirc
    if not device_spec:
        device_spec = 'flirc'
        default = True

    # Try to match requested device
    for path, name in devices:
        if device_spec.lower() in name.lower():
            _logger.info('Found device: {}'.format(name))
            return path

    # If user explicitly requested device, do NOT fallback
    if default is False and (device_spec or os.getenv('FS42_INPUT_DEVICE')):
        _logger.info("Device '{}' not found yet. Waiting...".format(device_spec))
        return None

    # Otherwise fallback to first keyboard device
    _logger.info('Using default device: {}'.format(devices[0][1]))
    return devices[0][0]


def get_key_name_from_code(key_code):
    """
    Convert evdev key code to readable key name
    """
    key_map = {
        ecodes.KEY_HOME: 'home',
        ecodes.KEY_END: 'end',
        ecodes.KEY_UP: 'up',
        ecodes.KEY_DOWN: 'down',
        ecodes.KEY_LEFT: 'left',
        ecodes.KEY_RIGHT: 'right',
        ecodes.KEY_SPACE: 'space',
        ecodes.KEY_ENTER: 'enter',
        ecodes.KEY_ESC: 'esc',
        ecodes.KEY_TAB: 'tab',
        ecodes.KEY_BACKSPACE: 'backspace',
        ecodes.KEY_DELETE: 'delete',
        ecodes.KEY_INSERT: 'insert',
        ecodes.KEY_PAGEUP: 'pageup',
        ecodes.KEY_PAGEDOWN: 'pagedown',
        ecodes.KEY_F1: 'f1',
        ecodes.KEY_F2: 'f2',
        ecodes.KEY_F3: 'f3',
        ecodes.KEY_F4: 'f4',
        ecodes.KEY_F5: 'f5',
        ecodes.KEY_F6: 'f6',
        ecodes.KEY_F7: 'f7',
        ecodes.KEY_F8: 'f8',
        ecodes.KEY_F9: 'f9',
        ecodes.KEY_F10: 'f10',
        ecodes.KEY_F11: 'f11',
        ecodes.KEY_F12: 'f12',
        ecodes.KEY_LEFTSHIFT: 'leftshift',
        ecodes.KEY_RIGHTSHIFT: 'rightshift',
        ecodes.KEY_LEFTCTRL: 'leftctrl',
        ecodes.KEY_RIGHTCTRL: 'rightctrl',
        ecodes.KEY_LEFTALT: 'leftalt',
        ecodes.KEY_RIGHTALT: 'rightalt',
    }

    # Add letter keys a-z using ecodes constants
    key_map[ecodes.KEY_A] = 'a'
    key_map[ecodes.KEY_B] = 'b'
    key_map[ecodes.KEY_C] = 'c'
    key_map[ecodes.KEY_D] = 'd'
    key_map[ecodes.KEY_E] = 'e'
    key_map[ecodes.KEY_F] = 'f'
    key_map[ecodes.KEY_G] = 'g'
    key_map[ecodes.KEY_H] = 'h'
    key_map[ecodes.KEY_I] = 'i'
    key_map[ecodes.KEY_J] = 'j'
    key_map[ecodes.KEY_K] = 'k'
    key_map[ecodes.KEY_L] = 'l'
    key_map[ecodes.KEY_M] = 'm'
    key_map[ecodes.KEY_N] = 'n'
    key_map[ecodes.KEY_O] = 'o'
    key_map[ecodes.KEY_P] = 'p'
    key_map[ecodes.KEY_Q] = 'q'
    key_map[ecodes.KEY_R] = 'r'
    key_map[ecodes.KEY_S] = 's'
    key_map[ecodes.KEY_T] = 't'
    key_map[ecodes.KEY_U] = 'u'
    key_map[ecodes.KEY_V] = 'v'
    key_map[ecodes.KEY_W] = 'w'
    key_map[ecodes.KEY_X] = 'x'
    key_map[ecodes.KEY_Y] = 'y'
    key_map[ecodes.KEY_Z] = 'z'

    return key_map.get(key_code)


MPV_ACTIONS = {
    'toggle_subtitles': ('playback.toggle_subtitles', {}),
    'cycle_subtitles': ('playback.subtitles', {}),
    'cycle_audio': ('playback.audio', {}),
    'play_pause': ('playback.play_pause', {}),
    'rewind': ('playback.seek_relative', {'seconds': -10}),
    'fast_forward': ('playback.seek_relative', {'seconds': 10}),
}

# Device configuration selects behavior by name; adding a mapping does not require
# another branch in the input loop. Lambdas resolve handlers when a key is pressed.
KEY_HANDLERS = {
    'show_guide': lambda: show_guide_pressed(),
    'show_on_demand': lambda: show_on_demand_pressed(),
    'volume_up': lambda: volume_up_pressed(),
    'volume_down': lambda: volume_down_pressed(),
    'mute': lambda: mute_pressed(),
    'channel_up': lambda: channel_up_pressed(),
    'channel_down': lambda: channel_down_pressed(),
    'last_channel': lambda: last_channel_pressed(),
    'power_stop': lambda: toggle_services() if USE_SYSTEMCTL else end_pressed(),
    **{name: (lambda action=name: mpv_command_pressed(action)) for name in MPV_ACTIONS},
}


def handle_key_name(key_name):
    """
    Handle a key press by key name (common logic for evdev and test mode)
    """
    if custom_guide_is_active():
        # Back navigates menus while one is visible; outside menus this key
        # retains its normal Last Channel (or controller Exit) mapping.
        if key_name in (KEY_MAPPINGS.get('last_channel'), 'esc'):
            send_custom_guide_key('Escape')
            return True
        guide_keys = {
            'up': 'ArrowUp',
            'down': 'ArrowDown',
            'left': 'ArrowLeft',
            'right': 'ArrowRight',
            'enter': 'Enter',
        }
        if key_name in guide_keys:
            send_custom_guide_key(guide_keys[key_name])
            return True

    # Check mappings and call appropriate function
    for function_name, mapped_key in KEY_MAPPINGS.items():
        if key_name == mapped_key:
            _logger.info('DEBUG: Matched function: {}'.format(function_name))
            if function_name == 'exit':
                _logger.info('Exiting remote controller...')
                return False
            handler = KEY_HANDLERS.get(function_name)
            if handler:
                handler()
            break

    if key_name in exec_mappings:
        try:
            _logger.info('{} {}'.format('Executing key callback: ', exec_mappings[key_name]))
            os.system(exec_mappings[key_name])
        except Exception as e:
            _logger.error('Error executing key callback')
            _logger.info(e)

    return True


def handle_key_event(event):
    """
    Handle key press events from evdev
    """
    if event.type == ecodes.EV_KEY and event.value == 1:  # Key press (not release)
        key_code = event.code

        # Number keys (1-9, 0) - always handled the same way
        if key_code >= ecodes.KEY_1 and key_code <= ecodes.KEY_9:
            number = key_code - ecodes.KEY_1 + 1
            number_pressed(number)
            return True
        elif key_code == ecodes.KEY_0:
            number_pressed(0)
            return True
        elif key_code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER):
            global channel_input_timer
            with input_lock:
                confirming = bool(channel_input)
                if confirming and channel_input_timer:
                    channel_input_timer.cancel()
                    channel_input_timer = None
            if confirming:
                send_channel_change()
                return True
            if custom_guide_is_active():
                send_custom_guide_key('Enter')
                return True

        # Get the key name and check if it's mapped to a function
        key_name = get_key_name_from_code(key_code)
        if not key_name:
            _logger.info('DEBUG: Unknown key code: {}'.format(key_code))
            return True

        _logger.info('DEBUG: Key pressed: {0} (code: {1})'.format(key_name, key_code))
        return handle_key_name(key_name)

    return True


def test_mode():
    """
    Run in test mode using stdin for input (for WSL/development)
    """
    _logger.info("\n" + '=' * 60)
    _logger.info('TEST MODE - Running without input device')
    _logger.info('=' * 60)
    _logger.info("\nAvailable commands:")
    _logger.info('  0-9: Channel selection')
    _logger.info('  h: Home/Guide')
    _logger.info('  u: Channel up')
    _logger.info('  d: Channel down')
    _logger.info('  l: Volume down (left)')
    _logger.info('  r: Volume up (right)')
    _logger.info('  m: Mute')
    _logger.info('  b: Last channel')
    _logger.info('  e: Power/End (toggle services)')
    _logger.info('  q: Quit')
    _logger.info("\nType a command and press Enter:")
    _logger.info('=' * 60 + "\n")

    while True:
        try:
            cmd = input('> ').strip().lower()

            if not cmd:
                continue

            # Handle numbers
            if cmd.isdigit():
                for digit in cmd:
                    number_pressed(int(digit))
                continue

            # Map single character commands to key names
            key_map = {
                'h': 'home',
                'u': 'up',
                'd': 'down',
                'l': 'left',
                'r': 'right',
                'm': 'm',
                'b': 'backspace',
                'e': 'end',
                'q': 'esc',
            }

            key_name = key_map.get(cmd)
            if key_name:
                if not handle_key_name(key_name):
                    break
            else:
                _logger.info('Unknown command: {}'.format(cmd))

        except KeyboardInterrupt:
            _logger.info("\nExiting remote controller...")
            break
        except EOFError:
            break


def main():
    """
    Main function to start the input device listener
    """
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='FieldStation42 Remote Controller', formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Device specification examples:
  -d /dev/input/event3      Use specific device path
  -d 0                      Use device at index 0 from the device list
  -d flirc                  Use first device with 'flirc' in its name
  -d keyboard               Use first device with 'keyboard' in its name
  -d test                   Run test mode

Environment variables:
  FS42_INPUT_DEVICE         Device specification (same format as -d)
  FS42_HOST                 Server host (default: 127.0.0.1)
  FS42_PORT                 Server port (default: 4242)
        """)
    parser.add_argument('-d', '--device', help='Input device to use (path, index, or name pattern)', default=None)
    parser.add_argument('--list-devices', action='store_true', help='List available input devices and exit')

    args = parser.parse_args()

    # Get device spec from args or environment variable
    device_spec = args.device or os.getenv('FS42_INPUT_DEVICE')

    _logger.info('Remote Controller started. Connecting to {}'.format(FS42_BASE_URL))

    # If --list-devices, just show devices and exit
    if args.list_devices:
        find_input_device(device_spec)
        return

    # Find input device
    if device_spec != 'test':
        device_path = find_input_device(device_spec)
    else:
        test_mode()

    _logger.info('Press ESC to exit.')

    first_run = True
    while True:
        try:
            if not device_path:
                _logger.info('Selected input not found. Retrying in 5 seconds...')
                time.sleep(5)
                # Check if the device has reconnected
                device_path = find_input_device(device_spec)

                if not device_path:
                    continue

            device = InputDevice(device_path)

            _logger.info('Listening for remote control commands from: {}'.format(device.name))

            # Main event loop
            for event in device.read_loop():
                if not handle_key_event(event):
                    return

        except OSError as e:
            # Bluetooth disconnect / USB unplug / device vanished
            if e.errno == 19 or e.errno == 2:
                _logger.info('Input device disconnected. Waiting for reconnection...')
                time.sleep(5)
            else:
                _logger.error('Device error: {}'.format(e))
                time.sleep(5)

        except FileNotFoundError:
            _logger.info('Input device missing. Waiting for reconnection...')
            time.sleep(5)

        except PermissionError:
            _logger.info('Permission denied. Try running with: sudo python3 -m fs42.tools.remote_control.main')
            sys.exit(1)

        except KeyboardInterrupt:
            _logger.info("\nExiting remote controller...")
            sys.exit(1)

        except Exception as e:
            _logger.error('Error: {}'.format(e))
            sys.exit(1)


def mpv_command_pressed(action):
    """
    Send a non-interrupting mpv runtime command to FS42
    """
    if not should_allow_press(action):
        return

    control, arguments = MPV_ACTIONS[action]

    try:
        response = post_control(control, arguments)

        if response.ok:
            _logger.info('MPV command sent: {}'.format(action))
        else:
            _logger.error('MPV command failed: {0} ({1})'.format(action, response.status_code))
    except Exception as e:
        _logger.error('MPV command error for {0}: {1}'.format(action, e))


if __name__ == '__main__':
    main()
