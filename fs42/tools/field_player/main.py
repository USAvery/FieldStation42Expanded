#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Parse playback options and run the field player
"""
import logging
import argparse

from fs42.core import logger
from fs42.core import decorators
from fs42.core.station_manager import StationConfigError


@decorators.error('FieldPlayer')
def main(argv=None):
    """
    Parse playback options and run the player
    """
    parser = argparse.ArgumentParser(description='FieldStation42 Player')
    parser.add_argument('-t', '--transition', choices=['long', 'short', 'none'],
                        help='Transition effect to use on channel change')
    parser.add_argument('-l', '--logfile', help='Set logging to use output file - will append each run')
    parser.add_argument('-v', '--verbose', action='store_true', help='Set logging verbosity level to very chatty')
    parser.add_argument('--no_server', action='store_true', help='Do not start the web API server process.')
    args = parser.parse_args(argv)
    logger.configure(verbose=args.verbose, logfile=args.logfile)

    # Load playback dependencies after parsing so help works without a display
    from fs42.tools.field_player.field_player import FieldPlayer
    try:
        return FieldPlayer(transition=args.transition, no_server=args.no_server).run()
    except StationConfigError as err:
        logging.getLogger('FieldPlayer').error(str(err))
        raise SystemExit(-1)
