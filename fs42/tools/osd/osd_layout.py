#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage osd layout
"""
from enum import Enum


class HAlignment(Enum):
    """
    HAlignment
    """
    LEFT = 'LEFT'
    RIGHT = 'RIGHT'
    CENTER = 'CENTER'


class VAlignment(Enum):
    """
    VAlignment
    """
    TOP = 'TOP'
    BOTTOM = 'BOTTOM'
    CENTER = 'CENTER'


def frac_to_margin_px(fraction, screen_dim_px):
    """
    Frac to margin px
    """
    return fraction * screen_dim_px / 2.0


def frac_to_size_px(fraction, screen_dim_px):
    """
    Frac to size px
    """
    return fraction * screen_dim_px


def resolve_top_left(
    screen_w,
    screen_h,
    content_w,
    content_h,
    halign,
    valign,
    x_margin_px,
    y_margin_px,
):
    """
    Resolve top left
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
