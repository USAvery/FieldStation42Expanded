#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Format player status and draw timed channel text with configurable font and placement
"""
from collections import defaultdict

from fs42.tools.osd._utils import resolve_font
from fs42.tools.osd.display.display import BaseDisplay


class StatusDisplay(BaseDisplay):
    """
    Display formatted player status text briefly after the text or playback state changes
    """

    def __init__(self, config):
        """
        Resolve the status font and read the initial player state

        :param config: (StatusDisplayConfig) status source, text formatting, placement, and timing
        """
        super(StatusDisplay, self).__init__(config)

        self._font = resolve_font(self.config.font, self.config.font_size)
        self._string = ''

        # Track the last status to detect changes
        self.last_status = None

        self.check_status()

    def check_status(self):
        """
        Read player status and restart the visibility timer when text or playback state changes

        Leave existing text unchanged for unreadable, empty, or invalid JSON. A changed
        state resets the timer to negative delay; an empty formatted string does not
        replace the previous text.
        """
        status = self._get_status()
        if not status:
            return

        # Check if status field changed (e.g., from "stopped" to "playing")
        status_changed = self.last_status is None or status.get('status') != self.last_status.get('status')
        self.last_status = status

        new_string = self.config.format_text.format_map(defaultdict(str, status))

        # Reset timer if text changed OR if status changed (like stopped->playing)
        if new_string != self._string or status_changed:
            self.time_since_change = -self.config.delay
            if new_string:
                self._string = new_string

    def is_visible(self):
        """
        Check whether status text exists and its display timer has not expired
        """
        return bool(self._string and super(StatusDisplay, self).is_visible())

    def draw(self, painter, screen_w, screen_h):
        """
        Paint visible status text using its configured alignment, color, and scale

        :param painter:  (QPainter) active painter for the OSD window
        :param screen_w: (int) drawing surface width in pixels
        :param screen_h: (int) drawing surface height in pixels
        """
        if not self.is_visible():
            return

        painter.setFont(self._font)
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(self._string) * self.config.expansion_factor
        text_h = metrics.height() * self.config.expansion_factor

        x, y = self._calc_draw_position(text_w, text_h, screen_w, screen_h)

        painter.setPen(self._color)
        if self.config.expansion_factor != 1.0:
            painter.save()
            painter.translate(x, y + metrics.ascent() * self.config.expansion_factor)
            painter.scale(self.config.expansion_factor, self.config.expansion_factor)
            painter.drawText(0, 0, self._string)
            painter.restore()
        else:
            painter.drawText(int(x), int(y + metrics.ascent()), self._string)
