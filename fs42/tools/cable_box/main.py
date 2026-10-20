#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Start the cable-box controller
"""


def main():
    """
    Load the device integration and run its event loop
    """
    from fs42.tools.cable_box.cable_box import CableBox
    CableBox().event_loop()


if __name__ == '__main__':
    main()
