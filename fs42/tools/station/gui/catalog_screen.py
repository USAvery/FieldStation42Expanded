#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Display station catalog statistics in the terminal interface and run selected or full catalog
rebuilds with progress feedback.
"""
from textual import work
from textual.app import Screen
from textual.widgets import Button
from textual.widgets import Header
from textual.widgets import Select
from textual.widgets import DataTable
from textual.containers import Vertical
from textual.containers import Horizontal

from fs42.tools.catalog.catalog import ShowCatalog
from fs42.core.station_manager import StationManager
from fs42.tools.station.gui.dialogs import LoadingScreen
from fs42.tools.station.gui.dialogs import SelectStationErr


class CatalogScreen(Screen):
    """
    Present catalog inspection and rebuild controls in the terminal administration interface
    """
    CSS_PATH = 'catalog_screen.tcss'

    def compose(self):
        """
        Create the station selector, catalog action buttons, and results table
        """
        yield Header('Welcome to Station42')
        self.dt = DataTable()

        self.options = []
        index = 0
        for station in StationManager().stations:
            if station['network_type'] != 'guide' and station['network_type'] != 'streaming':
                self.options.append((station['network_name'], index))
                index += 1
        self.select_station = Select(self.options, id='stationselector', prompt='Select Station')

        yield Vertical(
            Horizontal(
                self.select_station,
                Button('View Selected', id='view_selected', variant='success'),
                Button('(Re)build Selected', id='rebuild_selected', variant='success'),
                Button('(Re)build All', id='rebuild_all', variant='success'),
                Button('Back', id='back', variant='warning'),
            ),
            self.dt,
            id='catalogscreen',
        )

    async def on_button_pressed(self, event):
        """
        Dispatch catalog view, selected rebuild, all-station rebuild, and back actions
        """
        match event.button.id:
            case 'view_selected':
                val = self.select_station.value

                if val == Select.BLANK:
                    self.app.push_screen(SelectStationErr())
                else:
                    self.dt.clear(True)
                    (the_val, index) = self.options[val]
                    try:
                        catalog = ShowCatalog(StationManager().station_by_name(the_val))

                        self.dt.add_columns('Title', 'Tag', 'Duration', 'Hints')
                        for tag in catalog.clip_index:
                            if tag not in ['sign_off', 'off_air']:
                                for item in catalog.clip_index[tag]:
                                    if not isinstance(item, str):
                                        self.dt.add_row(item.title, item.tag, item.duration,
                                                        ','.join(map(str, item.hints)))
                    except FileNotFoundError:
                        self.dt.clear(True)
                        self.dt.add_column('Catalog not found.')

            case 'rebuild_selected':
                val = self.select_station.value
                if val == Select.BLANK:
                    self.app.push_screen(SelectStationErr())
                else:
                    self.dt.clear(True)
                    (the_val, index) = self.options[val]
                    ls = LoadingScreen()
                    self.app.push_screen(ls)
                    self.rebuild_thread(the_val)

            case 'rebuild_all':
                self.dt.clear(True)
                ls = LoadingScreen()
                self.app.push_screen(ls)
                self.rebuild_all_thread()

            case 'back':
                self.app.pop_screen()

    def on_mount(self):
        """
        Set the catalog screen title and table size, then populate station statistics
        """
        self.title = 'FieldStation42'
        self.sub_title = 'Control Panel'
        self.dt.styles.height = '85%'
        self.dt.styles.width = '100%'
        self.populate_stats()

    def on_screen_resume(self):
        """
        Refresh catalog statistics when returning to this screen
        """
        self.populate_stats()

    def rebuild_done(self):
        """
        Dismiss the rebuild progress dialog and refresh catalog statistics
        """
        self.app.pop_screen()
        self.populate_stats()

    def update_loading_message(self, message):
        """
        Replace the text shown in the active catalog progress dialog
        """
        self.app.query_one(LoadingScreen).set_message(message)

    @work(exclusive=True, thread=True)
    def rebuild_thread(self, network_name):
        """
        Rebuild the selected station's catalog in a worker and notify the interface on completion
        """
        station = StationManager().station_by_name(network_name)
        if station['network_type'] != 'guide' and station['network_type'] != 'streaming':
            ShowCatalog(station, rebuild_catalog=True)
        self.app.call_from_thread(self.rebuild_done)

    @work(exclusive=True, thread=True)
    def rebuild_all_thread(self):
        """
        Rebuild every non-guide, non-streaming station catalog in a worker thread
        """
        for station in StationManager().stations:
            # self.app.call_from_thread(self.update_loading_message, msg)
            if station['network_type'] != 'guide' and station['network_type'] != 'streaming':
                ShowCatalog(station, rebuild_catalog=True)
                # catalog.build_catalog()
        self.app.call_from_thread(self.rebuild_done)

    def populate_stats(self):
        """
        Replace the table with configured stations' catalog tag and media counts
        """
        self.dt.clear(True)
        self.dt.add_columns('Network', 'Channel', 'Type', 'Tags', 'Videos')
        for station in StationManager().stations:
            network_name = station['network_name']

            if 'catalog_path' in station:
                try:
                    (vcount, tcount) = ShowCatalog(station).summary_data()
                    self.dt.add_row(network_name, station['channel_number'], station['network_type'], vcount,
                                    tcount)
                except FileNotFoundError:
                    self.dt.add_row(network_name, station['channel_number'], station['network_type'], 'No catalog',
                                    'No catalog')
            else:
                pass
