#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage constants
"""

# Debounce Configuration - Time in seconds to wait between repeated button presses
DEBOUNCE_TIME = 0.25  # 250ms default debounce time

# Services to toggle when power button is pressed (remote-controller is never toggled)
SYSTEMCTL_TO_TOGGLE = [
    'fs42.service',  # Field Player
    'fs42-cable-box.service',  # Cable Box
    'fs42-osd.service',  # On-Screen Display
]

USE_SYSTEMCTL = True

# Key Mappings - Change these to customize which keys do what
# Available key names: 'home', 'end', 'up', 'down', 'left', 'right', 'space', 'enter',
# 'esc', 'tab', 'backspace', 'delete', 'insert', 'pageup', 'pagedown', 'f1'-'f12',
# 'a'-'z', 'leftshift', 'rightshift', 'leftctrl', 'rightctrl', 'leftalt', 'rightalt'
DEFAULT_KEY_MAPPINGS = {
    # Remote control functions
    'show_guide': 'home',  # Show program guide
    'volume_up': 'right',  # Increase volume
    'volume_down': 'left',  # Decrease volume
    'channel_up': 'up',  # Next channel
    'channel_down': 'down',  # Previous channel
    'last_channel': 'backspace',  # Switch to last channel
    'mute': 'm',  # Mute/unmute volume
    'toggle_subtitles': 'v',  # Toggle subtitle visibility in mpv
    'cycle_subtitles': 'j',  # Cycle subtitle tracks in mpv
    'cycle_audio': 'a',  # Cycle audio tracks in mpv
    'power_stop': 'end',  # Stop player (power button)
    'exit': 'esc',  # Exit remote controller

    # Alternative mappings (uncomment to use):
    # 'power_stop': 'space',     # Use spacebar for power/stop
    # 'show_guide': 'g',         # Use 'g' key for guide
    # 'volume_up': 'pageup',     # Use page up for volume up
    # 'volume_down': 'pagedown', # Use page down for volume down
}

SETTINGS_FILE = 'runtime/remote_controller.json'

CALLBACK_MAP_FILE = 'runtime/remote_callback_map.json'

PRESS_SOCKET = 'runtime/press.socket'
