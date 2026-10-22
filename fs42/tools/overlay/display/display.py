#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Share transparent window setup, screen scaling, drawing, and timer cleanup between overlays
"""
from PySide6.QtCore import Qt
from PySide6.QtCore import QRect
from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QApplication

from fs42.tools.overlay._constants import REFERENCE_WIDTH
from fs42.tools.overlay._constants import REFERENCE_HEIGHT


class BaseDisplay(QWidget):
    """
    Host a transparent overlay without taking focus or intercepting player input
    """

    finished = Signal()

    def __init__(self, parent=None):
        """
        Cover the primary screen and initialize a reusable update timer

        :param parent: (QWidget) optional Qt parent window
        """
        super(BaseDisplay, self).__init__(parent)
        self._timer = QTimer(self)
        screen = QApplication.primaryScreen()
        self._screen_geometry = screen.geometry() if screen else QRect(0, 0, REFERENCE_WIDTH, REFERENCE_HEIGHT)
        self._scale_factor = self._screen_geometry.height() / float(REFERENCE_HEIGHT)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.BlankCursor)
        self.setGeometry(self._screen_geometry)

    def scaled(self, value):
        """
        Convert a size specified for a 1080p screen to pixels on the current screen

        :param value: (float) reference size in pixels
        :return:      (int) scaled size, rounded down
        """
        return int(value * self._scale_factor)

    def _start_timer(self, interval, callback):
        """
        Poll messages or advance animation at the display's requested interval

        :param interval: (int) milliseconds between timer callbacks
        :param callback: (callable) display method invoked on each timer tick
        """
        self._timer.timeout.connect(callback)
        self._timer.start(interval)

    def _finish(self):
        """
        Stop display updates and notify the runner that this overlay is complete
        """
        self._timer.stop()
        self.finished.emit()

    def _draw(self, painter):
        """
        Require each display to paint its own content using the active window painter

        :param painter: (QPainter) painter already configured for smooth text and shapes
        """
        raise NotImplementedError

    def paintEvent(self, event):
        """
        Paint overlay content and release the painter even when drawing fails

        :param event: (QPaintEvent) notification that the window needs repainting
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        try:
            self._draw(painter)
        finally:
            painter.end()

    def closeEvent(self, event):
        """
        Stop pending updates before allowing Qt to close the overlay window

        :param event: (QCloseEvent) window-close request
        """
        self._timer.stop()
        super(BaseDisplay, self).closeEvent(event)
