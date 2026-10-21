#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Provide terminal-interface dialogs for progress, errors, station selection, and quit confirmation.
"""
from textual.widgets import Label
from textual.widgets import Button
from textual.widgets import Select
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import LoadingIndicator

from fs42.core.station_manager import StationManager


class LoadingScreen(ModalScreen):
    """
    Screen with a dialog to quit
    """

    CSS_PATH = 'dialogs.tcss'

    def compose(self):
        """
        Create the progress message and animated loading indicator
        """
        yield Vertical(
            Label('Working on it...', id='question'),
            LoadingIndicator(),
            id='dialog',
        )

    def set_message(self, message):
        """
        Replace the progress dialog's displayed message
        """
        self.query_one(Label).update(message)


class QuitScreen(ModalScreen):
    """
    Screen with a dialog to quit
    """

    CSS_PATH = 'dialogs.tcss'

    def compose(self):
        """
        Create the quit-confirmation message and cancel or exit buttons
        """
        yield Grid(
            Label('Are you sure you want to quit?', id='question'),
            Button('Cancel', variant='primary', id='cancel', classes='dialog_button'),
            Button('Quit', variant='error', id='quit', classes='dialog_button'),
            id='dialog',
        )

    def on_button_pressed(self, event):
        """
        Exit the administration app when confirmed, otherwise dismiss the quit dialog
        """
        if event.button.id == 'quit':
            self.app.exit()
        else:
            self.app.pop_screen()


class GeneralErr(ModalScreen):
    """
    Screen with a dialog to quit
    """

    CSS_PATH = 'dialogs.tcss'

    def compose(self):
        """
        Create an error message dialog with an acknowledgment button
        """
        yield Vertical(
            Label(self.message, id='question'),
            Button('Okay', variant='primary', id='quit', classes='dialog_button'),
            id='dialog',
        )

    def __init__(self, message):
        """
        Store the error message shown by this modal dialog
        """
        self.message = message
        super(GeneralErr, self).__init__()

    def on_button_pressed(self, event):
        """
        Dismiss the error dialog after acknowledgment
        """
        self.app.pop_screen()


class SelectStationErr(ModalScreen):
    """
    Screen with a dialog to quit
    """

    CSS_PATH = 'dialogs.tcss'

    def compose(self):
        """
        Create a reminder that an operation requires selecting a station first
        """
        yield Vertical(
            Label('Please select a station first', id='question'),
            Button('Okay', variant='primary', id='quit', classes='dialog_button'),
            id='dialog',
        )

    def on_button_pressed(self, event):
        """
        Dismiss the missing-station warning
        """
        self.app.pop_screen()


class SelectStationScreen(ModalScreen[str]):
    """
    Screen with a dialog to quit
    """

    CSS_PATH = 'dialogs.tcss'

    def compose(self):
        """
        Create a station chooser with confirm and cancel buttons
        """
        self.options = []
        index = 0
        for station in StationManager().stations:
            self.options.append((station['network_name'], index))
            index += 1
        self.select_station = Select(self.options, id='stationselector')

        yield Grid(
            Label('Select a station', id='question'),
            self.select_station,
            Button('Cancel', variant='primary', id='cmd_cancel', classes='dialog_button'),
            Button('Go!', variant='success', id='cmd_go', classes='dialog_button'),
            id='selectstation_dialog',
        )

    def on_button_pressed(self, event):
        """
        Close the chooser with the selected network name, or None when canceled or empty
        """
        if event.button.id == 'cmd_go':
            val = self.select_station.value
            if val == Select.BLANK:
                self.dismiss(None)
            else:
                (the_val, index) = self.options[val]
                self.dismiss(the_val)
        else:
            self.dismiss(None)
