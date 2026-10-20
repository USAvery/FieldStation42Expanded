#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage ux
"""
from textual.app import App

from fs42.tools.station.gui.welcome_screen import WelcomeScreen


class StationApp(App):
    """
    StationApp
    """
    SCREENS = {'WelcomeScreen': WelcomeScreen}

    def on_mount(self):
        """
        On mount
        """
        self.push_screen('WelcomeScreen')


if __name__ == '__main__':
    app = StationApp()
    app.run()
