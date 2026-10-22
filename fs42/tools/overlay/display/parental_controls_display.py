#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Draw the station PIN prompt and apply digit-count, error, and close messages from the player
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen
from PySide6.QtGui import QFont
from PySide6.QtCore import QRect

from fs42.tools.overlay._utils import create_colors
from fs42.tools.overlay._constants import PIN_LENGTH
from fs42.tools.overlay._constants import FONT_FAMILY
from fs42.tools.overlay._constants import PARENTAL_THEMES
from fs42.tools.overlay.display.display import BaseDisplay
from fs42.tools.overlay._constants import PARENTAL_BOX_WIDTH
from fs42.tools.overlay._constants import PARENTAL_BOX_HEIGHT
from fs42.tools.overlay._constants import DEFAULT_PARENTAL_THEME


class ParentalControlsDisplay(BaseDisplay):
    """
    Show a station PIN prompt while the player validates input and controls its lifetime
    """

    def __init__(self, network_name, theme_name=DEFAULT_PARENTAL_THEME, parent=None):
        """
        Center the PIN prompt and initialize its player-controlled digit and error indicators

        :param network_name: (str) locked station name shown in the prompt
        :param theme_name:   (str) visual theme name, falling back to classic
        :param parent:       (QWidget) optional Qt parent window
        """
        super(ParentalControlsDisplay, self).__init__(parent)
        self._network_name = network_name
        self._theme_name = theme_name
        self._theme = create_colors(PARENTAL_THEMES.get(theme_name, PARENTAL_THEMES[DEFAULT_PARENTAL_THEME]))
        self._digits = 0
        self._error = False
        width = self.scaled(PARENTAL_BOX_WIDTH)
        height = self.scaled(PARENTAL_BOX_HEIGHT)
        rect = self._screen_geometry
        self.setGeometry(rect.x() + (rect.width() - width) // 2,
                         rect.y() + (rect.height() - height) // 2, width, height)

    def apply_state(self, digits=None, error=False, close=False):
        """
        Update PIN indicators directly from a shared-service command without queue polling

        :param digits: (int) masked digit count, or None to keep the existing count
        :param error:  (bool) whether to show the incorrect-PIN message
        :param close:  (bool) whether to finish this presentation
        """
        if close:
            self._finish()
            return
        if digits is not None:
            self._digits = int(digits)
        self._error = bool(error)
        self.update()

    def _draw_line(self, painter, y, height, text, color):
        """
        Center one prompt line within the panel's horizontal text margins

        :param painter: (QPainter) active window painter with the desired font selected
        :param y:       (int) top position in 1080p reference pixels
        :param height:  (int) line height in reference pixels
        :param text:    (str) message to display
        :param color:   (QColor) text color for this line
        """
        rect = QRect(self.scaled(40), self.scaled(y), self.width() - self.scaled(80), self.scaled(height))
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_pin_boxes(self, painter):
        """
        Paint four PIN boxes and mask entered digits with asterisks

        :param painter: (QPainter) active window painter
        """
        size = self.scaled(48)
        gap = self.scaled(18)
        width = size * PIN_LENGTH + gap * (PIN_LENGTH - 1)
        x = (self.width() - width) // 2
        painter.setFont(QFont(FONT_FAMILY, self.scaled(30), QFont.Bold))
        for index in range(PIN_LENGTH):
            rect = QRect(x + index * (size + gap), self.scaled(168), size, size)
            painter.setPen(QPen(self._theme['border'], self.scaled(2)))
            painter.setBrush(self._theme['pin_box'])
            painter.drawRoundedRect(rect, self.scaled(6), self.scaled(6))
            if index < self._digits:
                painter.setPen(self._theme['text'])
                painter.drawText(rect, Qt.AlignCenter, '*')

    def _draw(self, painter):
        """
        Paint the station name, PIN indicators, error feedback, and channel-change hint

        :param painter: (QPainter) active window painter
        """
        rect = QRect(0, 0, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(self._theme['border'], self.scaled(3)))
        painter.setBrush(self._theme['box'])
        painter.drawRoundedRect(rect, self.scaled(14), self.scaled(14))
        painter.setFont(QFont(FONT_FAMILY, self.scaled(28), QFont.Bold))
        self._draw_line(painter, 28, 42, 'PARENTAL CONTROLS', self._theme['text'])
        painter.setFont(QFont(FONT_FAMILY, self.scaled(18)))
        self._draw_line(painter, 88, 36, '{} requires a PIN.'.format(self._network_name), self._theme['text'])
        message = 'Incorrect PIN. Try again.' if self._error else 'Enter PIN to continue.'
        color = self._theme['error'] if self._error else self._theme['message']
        self._draw_line(painter, 122, 34, message, color)
        self._draw_pin_boxes(painter)
        painter.setFont(QFont(FONT_FAMILY, self.scaled(14)))
        self._draw_line(painter, 232, 28, 'Use channel up/down to leave this station.', self._theme['muted'])
