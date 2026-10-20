#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Parse administration options and run the station tool
"""
import sys

from fs42.core import logger
from fs42.core import decorators
from fs42.tools.station import _utils
from fs42.tools.station.station import Station
from fs42.core.station_manager import StationConfigError


@decorators.error('Station42')
def main(argv=None):
    """
    Parse station options and run the selected operations
    """
    logger.configure(rich=True)
    args = _utils.build_parser().parse_args(argv)
    try:
        return Station(args, start_server=not (sys.argv[1:] if argv is None else argv)).run()
    except StationConfigError as err:
        logger.setup('Station42').error(str(err))
        raise SystemExit(-1)
