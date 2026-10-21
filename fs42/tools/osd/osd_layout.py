#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Convert fractional display sizes and margins into pixel coordinates and resolve element positions
for horizontal and vertical alignment.
"""
from enum import Enum


class HAlignment(Enum):
    """
    Choose which horizontal screen edge or center anchors an OSD element
    """
    LEFT = 'LEFT'
    RIGHT = 'RIGHT'
    CENTER = 'CENTER'


class VAlignment(Enum):
    """
    Choose which vertical screen edge or center anchors an OSD element
    """
    TOP = 'TOP'
    BOTTOM = 'BOTTOM'
    CENTER = 'CENTER'


def calc_margin_px(fraction, screen_dim_px):
    """
    Convert an OSD margin setting to the distance from the screen edge in pixels

    :param fraction:      (float) margin as a fraction of half the screen dimension
    :param screen_dim_px: (int) full screen width or height in pixels
    :return:              (float) edge distance in pixels, without rounding
    """
    return fraction * screen_dim_px / 2.0


def frac_to_size_px(fraction, screen_dim_px):
    """
    Convert an OSD size setting to a fraction of the full screen dimension

    :param fraction:      (float) proportion of the screen width or height to occupy
    :param screen_dim_px: (int) full screen width or height in pixels
    :return:              (float) content width or height in pixels, without rounding
    """
    return fraction * screen_dim_px


def calc_draw_position(screen_w, screen_h, content_w, content_h,
                       halign, valign, x_margin_px, y_margin_px):
    """
    Position an OSD element within the screen using its alignment and edge margins

    Center alignment ignores the margin on that axis. Coordinates are not rounded
    or clamped, so oversized content can extend beyond the screen.

    :param screen_w:    (int) screen width in pixels
    :param screen_h:    (int) screen height in pixels
    :param content_w:   (float) element width in pixels
    :param content_h:   (float) element height in pixels
    :param halign:      (HAlignment) horizontal anchor
    :param valign:      (VAlignment) vertical anchor
    :param x_margin_px: (float) inset from the left or right edge in pixels
    :param y_margin_px: (float) inset from the top or bottom edge in pixels
    :return:            (tuple) top-left x and y coordinates in pixels
    """

    if halign == HAlignment.LEFT:
        x = x_margin_px
    elif halign == HAlignment.RIGHT:
        x = screen_w - content_w - x_margin_px
    else:  # CENTER
        x = (screen_w - content_w) / 2.0

    if valign == VAlignment.TOP:
        y = y_margin_px
    elif valign == VAlignment.BOTTOM:
        y = screen_h - content_h - y_margin_px
    else:  # CENTER
        y = (screen_h - content_h) / 2.0

    return x, y
