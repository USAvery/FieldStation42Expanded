#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Present media-information text and timed fades inside the shared display service
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QPainter
from PySide6.QtGui import QFontMetrics

from fs42.tools.overlay._utils import load_font_family
from fs42.tools.overlay.display.display import BaseDisplay


class MediaInfoDisplay(BaseDisplay):
    """
    Cache styled NFO text and fade it at the beginning and end of a known playback duration
    """

    def __init__(self, lines, play_duration, show_seconds, overlay_cfg, parent=None):
        """
        Build one compact text pixmap and schedule optional hide and reappearance deadlines

        :param lines:         (list) ordered metadata lines
        :param play_duration: (float) playback length in seconds, or None for persistent display
        :param show_seconds:  (float) visible period at each end of long clips
        :param overlay_cfg:   (dict) configured font, color, text effect, and fade duration
        :param parent:        (QWidget) optional Qt parent window
        """
        super(MediaInfoDisplay, self).__init__(parent)
        self._config = overlay_cfg
        self._lines = lines[:2] if overlay_cfg['overlay_type'] == 'minimal' else lines
        self._opacity = 1.0
        self._fade_direction = 0
        self._hide_timer = QTimer(self)
        self._show_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._show_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._show_timer.timeout.connect(self._fade_in)
        self._timer.timeout.connect(self._fade_step)
        self._pixmap_origin = None
        self._pixmap = self._create_pixmap()
        if play_duration is not None and play_duration > show_seconds * 2:
            self._hide_timer.start(int(show_seconds * 1000))
            self._show_timer.start(int((play_duration - show_seconds) * 1000))

    def _create_pixmap(self):
        """
        Paint text and its effect once into a content-sized image reused for every fade frame
        """
        family = load_font_family(self._config['overlay_font_path'])
        fonts = []
        for prefix in ('title', 'body'):
            weight = QFont.Bold if self._config['overlay_{}_weight'.format(prefix)] == 'bold' else QFont.Normal
            fonts.append(QFont(family, self.scaled(self._config['overlay_{}_size'.format(prefix)]), weight))
        metrics = [QFontMetrics(font) for font in fonts]
        heights = [int(value.height() * 1.2) for value in metrics]
        effect = max(1, self.scaled(self._config['overlay_offset_px']))
        height = heights[0] + heights[1] * max(0, len(self._lines) - 1)
        width = max([metrics[min(index, 1)].horizontalAdvance(line)
                     for index, line in enumerate(self._lines)] or [1])
        rect = QRect(self.scaled(80) - effect, self._screen_geometry.height() - self.scaled(80) - height - effect,
                     width + effect * 2, height + effect * 2)
        self._set_content_rect(rect)
        pixmap = QPixmap(rect.size())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        y = effect
        try:
            for index, line in enumerate(self._lines):
                which = min(index, 1)
                painter.setFont(fonts[which])
                self._draw_line(painter, effect, y + metrics[which].ascent(), line, effect)
                y += heights[which]
        finally:
            painter.end()
        self._pixmap_origin = rect.topLeft()
        return pixmap

    def _draw_line(self, painter, x, y, text, extent):
        """
        Paint one text line over its configured diagonal shadow or eight-direction outline
        """
        if self._config['overlay_effect'] == 'drop_shadow':
            offsets = [(index, index) for index in range(1, extent + 1)]
        else:
            offsets = [(dx, dy) for dx in (-extent, 0, extent) for dy in (-extent, 0, extent) if dx or dy]
        painter.setPen(QColor(*self._config['overlay_shadow_color']))
        for dx, dy in offsets:
            painter.drawText(x + dx, y + dy, text)
        painter.setPen(QColor(*self._config['overlay_text_color']))
        painter.drawText(x, y, text)

    def _fade_out(self):
        """
        Start fading the initial metadata presentation toward a hidden middle section
        """
        self._fade_direction = -1
        self._timer.start(30)

    def _fade_in(self):
        """
        Restore the metadata window and fade it in for the final visibility period
        """
        self._opacity = 0.0
        self._fade_direction = 1
        self.show()
        self._timer.start(30)

    def _fade_step(self):
        """
        Advance opacity, repaint the cached image, and stop animation at either endpoint
        """
        steps = max(1, self._config['overlay_fade_duration_ms'] // 30)
        self._opacity = min(1.0, max(0.0, self._opacity + self._fade_direction / steps))
        self.update()
        if self._opacity in (0.0, 1.0):
            self._timer.stop()
            if self._opacity == 0.0:
                self.hide()

    def _draw(self, painter):
        """
        Composite the cached metadata text at its current fade opacity
        """
        painter.setOpacity(self._opacity)
        painter.drawPixmap(self._pixmap_origin, self._pixmap)
