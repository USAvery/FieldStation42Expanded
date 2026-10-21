#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Retain the previous decoded picture while the next channel loads.
"""
from PySide6.QtCore import Qt
from PySide6.QtCore import QRect
from PySide6.QtCore import QTimer
from PySide6.QtGui import QRegion
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QImageReader
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget


class TransitionWindow(QWidget):
    def __init__(self):
        """
        Create a reusable frame surface above the native playback window
        """
        super(TransitionWindow, self).__init__()
        self._pixmap = None
        self._preview_box = None
        self.setWindowTitle('FieldStation42 Channel Transition')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.BlankCursor)

    def show_frame(self, path, callback):
        """
        Map a retained video frame and acknowledge after Qt paints it

        :param path:     (str) native MPV screenshot filename
        :param callback: (callable) notification that the frame surface was mapped
        :return:          (bool) whether the image could be loaded
        """
        pixmap = QPixmap.fromImage(QImageReader(path).read())
        if pixmap.isNull():
            return False
        self._pixmap = pixmap
        self._preview_box = None
        self.showFullScreen()
        self.clearMask()
        self.raise_()
        self.update()
        QTimer.singleShot(35, callback)
        return True

    def set_preview(self, box=None):
        """
        Fit the retained picture into the guide hole or restore full screen
        """
        self._preview_box = box
        if box:
            self.setMask(QRegion(QRect(box['x'], box['y'], box['width'], box['height'])))
        else:
            self.clearMask()
        self.update()

    def paintEvent(self, event):
        """
        Paint the old picture with its original aspect and black padding
        """
        painter = QPainter(self)
        box = self._preview_box
        rect = QRect(box['x'], box['y'], box['width'], box['height']) if box else self.rect()
        painter.fillRect(rect, Qt.black)
        if self._pixmap is None:
            return
        size = self._pixmap.size()
        size.scale(rect.size(), Qt.KeepAspectRatio)
        target = QRect(0, 0, size.width(), size.height())
        target.moveCenter(rect.center())
        painter.drawPixmap(target, self._pixmap)
