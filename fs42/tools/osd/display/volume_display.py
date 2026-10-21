#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Consume mixer status messages and draw a temporary volume meter
"""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QPen

from fs42.core import logger as project_logger

from fs42.tools.osd.osd_layout import calc_margin_px
from fs42.tools.osd.osd_layout import frac_to_size_px
from fs42.tools.osd.display.display import BaseDisplay


_logger = project_logger.setup('fs42.tools.osd.display.volume_display')


class VolumeDisplay(BaseDisplay):
    """
    Show a temporary volume meter after consuming a mixer status message
    """

    def __init__(self, config):
        """
        Initialize the volume meter as hidden until the first valid message arrives

        :param config: (VolumeDisplayConfig) meter appearance, placement, and display duration
        """
        super(VolumeDisplay, self).__init__(config)

        self.volume = 0.0

        # Start hidden until we actually see a volume message.
        self.time_since_change = float('inf')

    def check_status(self):
        """
        Consume a volume status message and restart the meter's visibility timer

        Extract the first number from the volume field, clamp it to zero through one
        hundred percent, and attempt to empty the file after a valid reading. Ignore
        messages that cannot be read, decoded, or interpreted as a numeric volume.
        """
        status = self._get_status()
        if not status:
            return

        raw_volume = status.get('volume')
        if raw_volume is None:
            return

        # The volume field can arrive in several shapes depending on the mixer:
        # "75%", "MUTED (75%)", "unknown", "MUTE", etc. Pull the first number
        # out of whatever we get so a decorated string still drives the meter. If
        # there's no number at all (e.g. "unknown"), there's nothing to show.
        match = re.search(r'\d+(?:\.\d+)?', str(raw_volume))
        if not match:
            _logger.info('No volume level in volume status, {}'.format(raw_volume))
            return
        pct = float(match.group())

        self.volume = max(0.0, min(1.0, pct / 100.0))
        self.time_since_change = 0.0

        # Truncate the socket so that we only display each change once.
        try:
            with open(self._socket_file, 'w'):
                pass
        except OSError:
            pass

    def draw(self, painter, screen_w, screen_h):
        """
        Paint the visible meter's border and a fill proportional to the current volume

        :param painter:  (QPainter) active painter for the OSD window
        :param screen_w: (int) drawing surface width in pixels
        :param screen_h: (int) drawing surface height in pixels
        """
        if not self.is_visible():
            return

        w = frac_to_size_px(self.config.width, screen_w)
        h = frac_to_size_px(self.config.height, screen_h)
        x, y = self._calc_draw_position(w, h, screen_w, screen_h)

        painter.setPen(QPen(self._color, self.config.border_thickness))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(x), int(y), int(w), int(h))

        pad_x = calc_margin_px(self.config.padding, screen_w)
        pad_y = calc_margin_px(self.config.padding, screen_h)
        inner_h = h - 2.0 * pad_y
        inner_w = (w - 2.0 * pad_x) * self.volume
        if inner_w > 0.0 and inner_h > 0.0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._color)
            painter.drawRect(int(x + pad_x), int(y + pad_y), int(inner_w), int(inner_h))
