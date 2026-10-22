#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Start the single Qt service that hosts the OSD and on-demand playback panels
"""
import argparse


def main():
    """
    Parse optional discovery and OSD configuration paths and start the display service
    """
    parser = argparse.ArgumentParser(description='Run the shared FieldStation42 display service')
    parser.add_argument('--state-file', help='Private service discovery file')
    parser.add_argument('--osd-config', help='OSD display configuration file')
    parser.add_argument('--owner-token', help=argparse.SUPPRESS)
    args = parser.parse_args()
    from fs42.tools.display.display import DisplayService
    return DisplayService(args.state_file, args.osd_config, args.owner_token).run()


if __name__ == '__main__':
    raise SystemExit(main())
