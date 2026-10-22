#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Launch a now-playing display or scrolling announcement from command-line arguments
"""
import argparse

from fs42.tools.overlay import _constants
from fs42.tools.overlay.overlay import Overlay


def main():
    """
    Parse the selected panel's inputs and keep its shared-service presentation alive
    """
    parser = argparse.ArgumentParser(description='Display an on-demand FieldStation42 overlay')
    commands = parser.add_subparsers(dest='overlay_type', required=True)
    now_playing = commands.add_parser('now_playing', help='Show metadata until the overlay is closed')
    now_playing.add_argument('file_path')
    now_playing.add_argument('db_path')
    ticker = commands.add_parser('ticker', help='Scroll an announcement and exit after its final repeat')
    ticker.add_argument('text', nargs='?', default=_constants.DEFAULT_TICKER_TEXT)
    ticker.add_argument('--title', default=_constants.DEFAULT_TICKER_TITLE)
    ticker.add_argument('--style', choices=tuple(_constants.TICKER_THEMES),
                        default=_constants.DEFAULT_TICKER_STYLE)
    ticker.add_argument('--iterations', type=int, default=_constants.DEFAULT_TICKER_ITERATIONS)
    options = vars(parser.parse_args())
    overlay_type = options.pop('overlay_type')
    return Overlay(overlay_type, **options).run()


if __name__ == '__main__':
    raise SystemExit(main())
