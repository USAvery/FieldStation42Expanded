#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage welcome screen
"""
from textual.app import Screen
from textual.widgets import Button
from textual.widgets import Header
from textual.widgets import Markdown
from textual.containers import Horizontal

from fs42.tools.catalog.catalog import ShowCatalog
from fs42.core.station_manager import StationManager
from fs42.tools.station.gui.dialogs import QuitScreen
from fs42.tools.schedule.liquid_manager import LiquidManager
from fs42.tools.station.gui.catalog_screen import CatalogScreen
from fs42.tools.station.gui.schedule_screen import ScheduleScreen


class WelcomeScreen(Screen):
    """
    WelcomeScreen
    """
    CSS_PATH = 'welcome_screen.tcss'

    def compose(self):
        """
        Compose
        """
        yield Header('Welcome to Station42')
        self.md = Markdown('LOADING...')
        yield self.md
        yield Horizontal(
            Button('Manage Catalogs', id='manage_catalog', variant='success'),
            Button('Manage Schedules', id='manage_schedule', variant='primary'),
            Button('Exit Application', id='exit', variant='warning'),
            id='welcomebutton',
        )

    def on_button_pressed(self, event):
        """
        On button pressed
        """
        match event.button.id:
            case 'manage_catalog':
                self.app.push_screen(CatalogScreen())
            case 'manage_schedule':
                self.app.push_screen(ScheduleScreen())
            case 'exit':
                self.app.push_screen(QuitScreen())

    def on_mount(self):
        """
        On mount
        """
        self.title = 'FieldStation42'
        self.sub_title = 'Control Panel'
        self.md.styles.height = '80%'
        self.md.styles.width = '100%'
        self.populate_stats()

    def on_screen_resume(self):
        """
        On screen resume
        """
        self.populate_stats()

    def populate_stats(self):
        """
        Populate stats
        """
        self.md.update('')
        text = "# FieldStation42 Summary\n"

        for station in StationManager().stations:
            network_name = station['network_name']
            text += '## Network: {0} - Channel #{1} ({2})\n'.format(network_name, station['channel_number'],
                                                                    station['network_type'])

            if 'catalog_path' in station and station['network_type'] not in StationManager().no_catalog:
                catalog_exists = False
                try:
                    cat = ShowCatalog(station, False)
                    text += 'Catalog summary: {}\n\n'.format(cat.summary())
                    catalog_exists = True
                except FileNotFoundError:
                    text += "Catalog not found. Click 'Manage Catalogs' to build new catalog.\n\n"
                    catalog_exists = False

                (start, end) = (None, None)
                try:
                    (start, end) = LiquidManager().get_extents(network_name)
                except ValueError:
                    text += "* Schedule not found. This is an error - check your configuration.\n"

                if start and end:
                    text += '* Schedule extents: {0:%Y-%m-%d} to {1:%Y-%m-%d}\n'.format(start, end)
                else:
                    if catalog_exists:
                        text += "* Schedule not found. Click 'Manage Schedules' to generate schedules."
                    else:
                        text += "* Schedule not found. After building the catalog, click 'Manage Schedules' to generate schedules."
            else:
                if station['network_type'] in StationManager().no_catalog:
                    text += '* {} channels do not have catalogs or schedules\n'.format(station['network_type'])
                else:
                    text += '* Catalog not configured or missing - check channel configuration.'
            text += "\n"
        self.md.update(text)
