#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Start the on-screen display
"""
import sys

from PySide6.QtWidgets import QApplication

from fs42.tools.osd.osd import OsdWindow
from fs42.tools.osd._api import load_objects


def main():
    """
    Create the configured OSD elements and run the persistent Qt display event loop
    """
    app = QApplication(sys.argv)
    objects = load_objects()
    window = OsdWindow(objects)
    # _tick() shows the overlay only when at least one OSD element is visible.
    window._tick()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
