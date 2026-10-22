#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Scroll a themed announcement across a broadcast-style panel and signal completion after its final repeat
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPen
from PySide6.QtGui import QFont
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor
from PySide6.QtGui import QPixmap
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFontMetrics
from PySide6.QtGui import QLinearGradient

from fs42.tools.overlay import _constants
from fs42.tools.overlay._utils import create_colors
from fs42.tools.overlay.display.display import BaseDisplay


class TickerDisplay(BaseDisplay):
    """
    Scroll an announcement below a fixed header and finish after its requested repetitions
    """

    def __init__(self, text, title=_constants.DEFAULT_TICKER_TITLE,
                 style=_constants.DEFAULT_TICKER_STYLE, iterations=_constants.DEFAULT_TICKER_ITERATIONS,
                 parent=None):
        """
        Prepare the announcement, themed colors, header logo, and scrolling timer

        :param text:       (str) announcement text to scroll
        :param title:      (str) fixed header text above the announcement
        :param style:      (str) color scheme, falling back to fieldstation
        :param iterations: (int) complete scrolls to display before finishing
        :param parent:     (QWidget) optional Qt parent window
        """
        super(TickerDisplay, self).__init__(parent)
        self._text = text
        self._title = title
        self._style = style
        self._iterations = iterations
        self._current_iterations = 0
        self._scroll_position = _constants.TICKER_WIDTH - _constants.TICKER_MARGIN
        self._font = QFont(_constants.FONT_FAMILY, 20, QFont.Bold)
        self._header_font = QFont(_constants.FONT_FAMILY, 12, QFont.Bold)
        self._text_color = QColor(255, 255, 255)
        theme = _constants.TICKER_THEMES.get(style, _constants.TICKER_THEMES[_constants.DEFAULT_TICKER_STYLE])
        self._colors = create_colors(theme)
        self._logo = self._load_logo()
        self._set_content_rect(self._get_panel_rect())
        self._start_timer(_constants.TICKER_INTERVAL_MS, self._scroll_text)

    def _load_logo(self):
        """
        Load the optional runtime logo and shrink it to fit the ticker header

        :return: (QPixmap) scaled logo, or None when absent or undecodable
        """
        path = _constants.TICKER_LOGO_PATH
        if not os.path.exists(path):
            return None
        logo = QPixmap(path)
        if logo.isNull():
            return None
        height = int(_constants.TICKER_HEADER_HEIGHT * 0.8)
        return logo.scaledToHeight(height, Qt.SmoothTransformation) if logo.height() > height else logo

    def _scroll_text(self):
        """
        Move the announcement left and finish after the last complete scroll
        """
        if not self._text:
            self._finish()
            return
        width = QFontMetrics(self._font).horizontalAdvance(self._text)
        self._scroll_position -= _constants.TICKER_SCROLL_STEP_PX
        if self._scroll_position < -width:
            self._current_iterations += 1
            self._scroll_position = _constants.TICKER_WIDTH - _constants.TICKER_MARGIN
            if self._current_iterations >= self._iterations:
                self._finish()
                return
        self.update()

    def _get_header_rect(self, rect):
        """
        Size the fixed ticker header to fit its title and optional logo

        :param rect: (QRect) bounds of the complete ticker panel
        :return:     (QRect) header tab bounds in window coordinates
        """
        width = QFontMetrics(self._header_font).horizontalAdvance(self._title)
        if self._logo:
            width += self._logo.width() + _constants.TICKER_LOGO_SPACING
        width += _constants.TICKER_MARGIN * 2
        return rect.adjusted(2, 2, -(_constants.TICKER_WIDTH - width - 2),
                             -(_constants.TICKER_HEIGHT - _constants.TICKER_HEADER_HEIGHT))

    def _draw_header_background(self, painter, rect):
        """
        Paint the gradient header tab and its lower accent line

        :param painter: (QPainter) active window painter
        :param rect:    (QRect) header tab bounds
        """
        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0, self._colors['header_start'])
        gradient.setColorAt(1, self._colors['header_end'])
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 6, 6)
        painter.drawRect(rect.adjusted(0, rect.height() // 2, 0, 0))
        painter.setPen(QPen(self._colors['accent'], 1))
        painter.drawLine(QPointF(rect.bottomLeft()) + QPointF(6, 0),
                         QPointF(rect.bottomRight()) - QPointF(6, 0))

    def _draw_header(self, painter, rect):
        """
        Paint the fixed title and optional logo over the gradient header

        :param painter: (QPainter) active window painter
        :param rect:    (QRect) header tab bounds
        """
        self._draw_header_background(painter, rect)
        painter.setFont(self._header_font)
        x = rect.left() + _constants.TICKER_MARGIN
        if self._logo:
            y = rect.top() + (rect.height() - self._logo.height()) // 2
            painter.drawPixmap(x, y, self._logo)
            x += self._logo.width() + _constants.TICKER_LOGO_SPACING
        text_rect = rect.adjusted(x - rect.left(), 0, -_constants.TICKER_MARGIN, 0)
        painter.setPen(self._colors['text_shadow'])
        painter.drawText(text_rect.adjusted(1, 1, 1, 1), Qt.AlignLeft | Qt.AlignVCenter, self._title)
        painter.setPen(self._text_color)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self._title)

    def _draw_message(self, painter, rect, main_rect):
        """
        Clip the moving announcement to the body panel and paint its text shadow

        :param painter:   (QPainter) active window painter
        :param rect:      (QRect) bounds of the complete ticker panel
        :param main_rect: (QRect) message-panel bounds beneath the header
        """
        painter.setFont(self._font)
        y = rect.top() + _constants.TICKER_HEADER_HEIGHT + main_rect.height() // 2 + 6
        x = rect.left() + self._scroll_position
        painter.setClipRect(main_rect.adjusted(_constants.TICKER_MARGIN, 4, -_constants.TICKER_MARGIN, -4))
        painter.setPen(self._colors['text_shadow'])
        painter.drawText(x + 1, y + 1, self._text)
        painter.setPen(self._text_color)
        painter.drawText(x, y, self._text)

    def _get_panel_rect(self):
        """
        Locate the ticker panel near the bottom center of the primary screen
        """
        x = (self._screen_geometry.width() - _constants.TICKER_WIDTH) // 2
        y = self._screen_geometry.height() - _constants.TICKER_HEIGHT - _constants.TICKER_BOTTOM_MARGIN
        return QRect(x, y, _constants.TICKER_WIDTH, _constants.TICKER_HEIGHT)

    def _draw(self, painter):
        """
        Paint the bottom-centered ticker panel, fixed header, and scrolling message

        :param painter: (QPainter) active window painter
        """
        rect = self._get_panel_rect()
        main_rect = rect.adjusted(2, _constants.TICKER_HEADER_HEIGHT, -2, -2)
        painter.setBrush(self._colors['background'])
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(main_rect, 4, 4)
        self._draw_header(painter, self._get_header_rect(rect))
        if self._text:
            self._draw_message(painter, rect, main_rect)
