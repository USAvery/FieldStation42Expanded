#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose shared-service presentations for now-playing metadata, scrolling announcements, and station PIN prompts
"""
from fs42.tools.overlay.overlay import Overlay
from fs42.tools.overlay._constants import DEFAULT_TICKER_TITLE
from fs42.tools.overlay._constants import DEFAULT_TICKER_STYLE
from fs42.tools.overlay._constants import DEFAULT_PARENTAL_THEME
from fs42.tools.overlay._constants import DEFAULT_TICKER_ITERATIONS


def run_now_playing(file_path, db_path):
    """
    Show audio metadata until the player hides or replaces the presentation

    :param file_path: (str) playing media path used for metadata lookup
    :param db_path:   (str) metadata database filename
    :return:          (PanelHandle) presentation controlled by the player
    """
    return Overlay('now_playing', file_path=file_path, db_path=db_path).start()


def run_ticker(text, title=DEFAULT_TICKER_TITLE, style=DEFAULT_TICKER_STYLE,
               iterations=DEFAULT_TICKER_ITERATIONS):
    """
    Show a scrolling announcement that hides after its requested repetitions

    :param text:       (str) announcement text to scroll
    :param title:      (str) fixed header text
    :param style:      (str) ticker color-scheme name
    :param iterations: (int) complete scrolls before the announcement hides
    :return:           (PanelHandle) scrolling presentation in the shared service
    """
    return Overlay('ticker', text=text, title=title, style=style, iterations=iterations).start()


def run_parental_controls(network_name, theme_name=DEFAULT_PARENTAL_THEME):
    """
    Show a station PIN prompt controlled by direct digit-count and error-state updates

    :param network_name: (str) locked station name shown in the prompt
    :param theme_name:   (str) PIN-prompt color theme
    :return:             (PanelHandle) PIN prompt controlled by the player
    """
    return Overlay('parental_controls', network_name=network_name, theme_name=theme_name).start()
