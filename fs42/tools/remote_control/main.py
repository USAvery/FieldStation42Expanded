#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Start the remote-input controller
"""


def main():
    """
    Load the input-device integration and run the controller
    """
    from fs42.tools.remote_control.remote_control import main as run
    run()


if __name__ == '__main__':
    main()
