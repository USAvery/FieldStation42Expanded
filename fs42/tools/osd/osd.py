#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build the persistent transparent display window and its configured status, volume, and logo
elements. Poll runtime state and hide the window when no element is visible.
"""
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QElapsedTimer
from PySide6.QtWidgets import QApplication

from fs42.tools.osd.display.status_display import StatusDisplay


class OsdWindow(QWidget):
    """
    Host OSD elements in a transparent window and poll their state even while hidden
    """

    def __init__(self, objects):
        """
        Create a screen-sized transparent window and start polling display elements

        :param objects: (list) elements implementing update and draw, optionally is_visible
        """
        super(OsdWindow, self).__init__()
        self.objects = objects
        self._window_visible = False

        self.setWindowFlags(Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.Tool
                            | Qt.WindowDoesNotAcceptFocus
                            | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.BlankCursor)
        self.setWindowTitle('FieldStation42 OSD')

        screen = QApplication.primaryScreen()
        geom = screen.geometry() if screen else None
        if geom is not None:
            self.setGeometry(geom)

        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._last_ns = self._elapsed.nsecsElapsed()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        # Poll status at 10 Hz. The old code repainted a full-screen transparent
        # surface at 30 FPS even while every OSD element was hidden.
        self.timer.start(100)

    def _object_is_visible(self, obj):
        """
        Check an element's visibility, assuming visible if its visibility hook is absent or fails
        """
        visible_fn = getattr(obj, 'is_visible', None)
        if visible_fn is None:
            return True
        try:
            return bool(visible_fn())
        except Exception:
            return True

    def _object_is_animated(self, obj):
        """
        Check whether an element is both visible and marked as animated
        """
        return bool(self._object_is_visible(obj) and getattr(obj, 'is_animated', False))

    def _tick(self):
        """
        Update display state, hide an empty window, and adjust polling to visible content

        Poll hidden content every 250 milliseconds, static content every 100 milliseconds,
        and visible animation approximately thirty times per second.
        """
        now_ns = self._elapsed.nsecsElapsed()
        dt = (now_ns - self._last_ns) / 1e9
        self._last_ns = now_ns

        for obj in self.objects:
            obj.update(dt)

        any_visible = any(self._object_is_visible(obj) for obj in self.objects)
        any_animated = any(self._object_is_animated(obj) for obj in self.objects)

        if any_visible:
            if not self._window_visible:
                self.show()
                self._window_visible = True

            # Static OSD elements only need a repaint when the 10 Hz state poll
            # runs. Animated logos temporarily restore the old 30 FPS cadence.
            self.timer.setInterval(int(1000 / 30) if any_animated else 100)
            self.update()
        else:
            # Removing the transparent full-screen surface lets the compositor
            # skip blending it on every display refresh.
            if self._window_visible:
                self.hide()
                self._window_visible = False
            self.timer.setInterval(250)

    def paintEvent(self, event):
        """
        Paint display elements with status text layered above the other elements

        :param event: (QPaintEvent) Qt repaint notification; the whole window is redrawn
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(
            QPainter.SmoothPixmapTransform)  # bilinear-scale logos, matching the old GL_LINEAR filtering

        w, h = self.width(), self.height()
        # Draw objects with StatusDisplay on top, same ordering as before.
        for obj in sorted(self.objects, key=lambda o: isinstance(o, StatusDisplay)):
            obj.draw(painter, w, h)

        painter.end()
