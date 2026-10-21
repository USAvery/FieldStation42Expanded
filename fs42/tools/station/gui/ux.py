#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Start the Textual station-administration application on its welcome screen.
"""
from textual.app import App

from fs42.tools.station.gui.welcome_screen import WelcomeScreen


class StationApp(App):
    """
    Host the terminal-based station administration screens and navigation
    """
    SCREENS = {'WelcomeScreen': WelcomeScreen}

    def on_mount(self):
        """
        Open the welcome screen when the administration app starts
        """
        self.push_screen('WelcomeScreen')


if __name__ == '__main__':
    app = StationApp()
    app.run()
