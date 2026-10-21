#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Share status-file reading, placement, and visibility timing between OSD displays
"""
import json

from PySide6.QtGui import QColor

from fs42.core import logger as project_logger

from fs42.tools.osd.osd_layout import calc_margin_px
from fs42.tools.osd.osd_layout import calc_draw_position


_logger = project_logger.setup('fs42.tools.osd.display.display')


class BaseDisplay(object):
    """
    Provide common display state and require subclasses to interpret and paint their content
    """

    def __init__(self, config):
        """
        Store display configuration, initialize its timer, and resolve its drawing color

        :param config: (obj) display configuration with timing and optional socket_file settings
        """
        self.config = config
        self.time_since_change = 0

        self._socket_file = getattr(config, 'socket_file', None)

        self._color = getattr(self.config, 'color', None) or getattr(self.config, 'text_color', (0, 255, 0, 200))
        self._color = QColor(*self._color) if self._color else None

    def _get_status(self):
        """
        Read JSON from the configured status file when it exists and contains text

        :return: (dict) status dictionary, or None for missing, unreadable, empty, or invalid status
        """
        if not self._socket_file:
            return

        try:
            with open(self._socket_file, 'r') as fin:
                content = fin.read()
        except OSError:
            return

        if not content.strip():
            return

        try:
            status = json.loads(content)
            return status if isinstance(status, dict) else None
        except (json.JSONDecodeError, ValueError):
            _logger.warning('Unable to parse {} status, {}'.format(self.__class__.__name__, content))
            return

    def _calc_draw_position(self, content_w, content_h, screen_w, screen_h):
        """
        Calculate the position for an OSD element within the screen

        :param content_w: (float) element width in pixels
        :param content_h: (float) element height in pixels
        :param screen_w:  (int) screen width in pixels
        :param screen_h:  (int) screen height in pixels
        :return:          (tuple) top-left x and y coordinates in pixels
        """
        x, y = calc_draw_position(screen_w, screen_h, content_w, content_h,
                                  self.config.halign, self.config.valign,
                                  calc_margin_px(self.config.x_margin, screen_w),
                                  calc_margin_px(self.config.y_margin, screen_h))
        return x, y

    def check_status(self):
        """
        Require subclasses to read status and update their content and visibility timer
        """
        raise NotImplementedError

    def update(self, dt):
        """
        Advance the visibility timer and invoke the status-change hook

        :param dt: (float) elapsed time since the previous update in seconds
        """
        self.time_since_change += dt
        self.check_status()

    def is_visible(self):
        """
        Check whether the display timer is still below the configured duration
        """
        return self.time_since_change < self.config.display_time

    def draw(self, painter, screen_w, screen_h):
        """
        Require subclasses to paint their visible content onto the OSD window

        :param painter:  (QPainter) active painter for the OSD window
        :param screen_w: (int) drawing surface width in pixels
        :param screen_h: (int) drawing surface height in pixels
        """
        raise NotImplementedError
