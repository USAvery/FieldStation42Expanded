#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Draw cached audio metadata in a persistent shaded panel near the lower screen edge
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor
from PySide6.QtGui import QFontMetrics
from PySide6.QtGui import QLinearGradient

from fs42.tools.overlay import _constants
from fs42.tools.overlay._utils import read_metadata
from fs42.tools.overlay._utils import create_colors
from fs42.tools.overlay.display.display import BaseDisplay


class NowPlayingDisplay(BaseDisplay):
    """
    Show track title, artist, and album until the player hides or replaces the panel
    """

    def __init__(self, file_path, db_path, parent=None):
        """
        Load track metadata and scale its panel and fonts to the primary screen

        :param file_path: (str) playing media path used for metadata lookup
        :param db_path:   (str) metadata database filename
        :param parent:    (QWidget) optional Qt parent window
        """
        super(NowPlayingDisplay, self).__init__(parent)
        self._file_path = file_path
        self._db_path = db_path
        self._metadata = read_metadata(file_path, db_path)
        self._box_width = self.scaled(_constants.NOW_PLAYING_WIDTH)
        self._box_height = self.scaled(_constants.NOW_PLAYING_HEIGHT)
        self._margin_x = self.scaled(_constants.NOW_PLAYING_MARGIN)
        self._margin_y = self.scaled(_constants.NOW_PLAYING_MARGIN)
        self._padding = self.scaled(_constants.NOW_PLAYING_PADDING)
        self._colors = create_colors(_constants.NOW_PLAYING_COLORS)
        self._title_font = QFont(_constants.FONT_FAMILY, self.scaled(_constants.NOW_PLAYING_TITLE_SIZE),
                                 QFont.Bold)
        self._info_font = QFont(_constants.FONT_FAMILY, self.scaled(_constants.NOW_PLAYING_INFO_SIZE),
                                QFont.Normal)
        self._set_content_rect(self._get_box_rect())

    def _get_box_rect(self):
        """
        Size the lower-left metadata panel to fit its longest text line and fading edge

        :return: (QRect) panel bounds in window coordinates
        """
        title_metrics = QFontMetrics(self._title_font)
        info_metrics = QFontMetrics(self._info_font)
        text_width = title_metrics.horizontalAdvance(self._metadata['title'])
        for field in ('artist', 'album'):
            if self._metadata[field]:
                text_width = max(text_width, info_metrics.horizontalAdvance(self._metadata[field]))
        fade_width = self.scaled(_constants.NOW_PLAYING_FADE_WIDTH)
        width = max(self._box_width, text_width + self._padding * 2 + fade_width)
        return QRect(self._margin_x, self._screen_geometry.height() - self._box_height - self._margin_y,
                     width, self._box_height)

    def _draw_background(self, painter, rect):
        """
        Shade the metadata panel and fade its right edge to transparency

        :param painter: (QPainter) active window painter
        :param rect:    (QRect) metadata panel bounds
        """
        gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
        gradient.setColorAt(0.0, self._colors['background_start'])
        gradient.setColorAt(0.7, self._colors['background_end'])
        fade_start = QColor(self._colors['background_end'])
        fade_start.setAlpha(180)
        gradient.setColorAt(0.85, fade_start)
        fade_end = QColor(self._colors['background_end'])
        fade_end.setAlpha(0)
        gradient.setColorAt(1.0, fade_end)
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 8, 8)

    def _draw_text(self, painter, x, y, text):
        """
        Paint a metadata line over an offset shadow for readability

        :param painter: (QPainter) active window painter with the desired font selected
        :param x:       (int) left edge of the text in pixels
        :param y:       (int) text baseline in pixels
        :param text:    (str) title, artist, or album text
        """
        offset = self.scaled(_constants.NOW_PLAYING_SHADOW_OFFSET)
        painter.setPen(self._colors['text_shadow'])
        painter.drawText(x + offset, y + offset, text)
        painter.setPen(self._colors['text'])
        painter.drawText(x, y, text)

    def _draw(self, painter):
        """
        Paint the metadata panel with a title and any available artist and album lines

        :param painter: (QPainter) active window painter
        """
        rect = self._get_box_rect()
        self._draw_background(painter, rect)
        x = rect.left() + self._padding
        y = rect.top() + self._padding
        painter.setFont(self._title_font)
        self._draw_text(painter, x, y + self.scaled(_constants.NOW_PLAYING_TITLE_SIZE), self._metadata['title'])
        painter.setFont(self._info_font)
        y += self.scaled(_constants.NOW_PLAYING_LINE_HEIGHT)
        for field in ('artist', 'album'):
            if self._metadata[field]:
                baseline = y + self.scaled(_constants.NOW_PLAYING_INFO_SIZE)
                self._draw_text(painter, x, baseline, self._metadata[field])
                y += self.scaled(_constants.NOW_PLAYING_LINE_HEIGHT)
