#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify fractional display sizes, margins, and alignment combinations resolve to the expected Qt
pixel coordinates.
"""
import pytest

from fs42.tools.osd.osd_layout import HAlignment
from fs42.tools.osd.osd_layout import VAlignment
from fs42.tools.osd.osd_layout import frac_to_size_px
from fs42.tools.osd.osd_layout import calc_draw_position
from fs42.tools.osd.osd_layout import calc_margin_px

SCREEN_W = 1920.0
SCREEN_H = 1080.0


class TestFracConversions(object):
    """
    Verify OSD sizes use full screen dimensions while margins use half dimensions
    """

    def test_margin_is_fraction_of_half_dimension(self):
        """
        Check margin is fraction of half dimension
        """
        # VolumeDisplayConfig default x_margin=0.1 on a 1920-wide screen -> 96px
        assert calc_margin_px(0.1, SCREEN_W) == pytest.approx(96.0)

    def test_size_is_fraction_of_full_dimension(self):
        """
        Check size is fraction of full dimension
        """
        # VolumeDisplayConfig default width=0.4 on a 1920-wide screen -> 768px
        assert frac_to_size_px(0.4, SCREEN_W) == pytest.approx(768.0)


class TestResolveTopLeft(object):
    """
    Verify aligned OSD coordinates account for element size and screen-edge margins
    """
    CONTENT_W = 200.0
    CONTENT_H = 50.0
    X_MARGIN = 20.0
    Y_MARGIN = 10.0

    @pytest.mark.parametrize(
        'halign,valign,expected_x,expected_y',
        [
            (HAlignment.LEFT, VAlignment.TOP, 20.0, 10.0),
            (HAlignment.LEFT, VAlignment.BOTTOM, 20.0, 1080.0 - 50.0 - 10.0),
            (HAlignment.LEFT, VAlignment.CENTER, 20.0, (1080.0 - 50.0) / 2.0),
            (HAlignment.RIGHT, VAlignment.TOP, 1920.0 - 200.0 - 20.0, 10.0),
            (HAlignment.RIGHT, VAlignment.BOTTOM, 1920.0 - 200.0 - 20.0, 1080.0 - 50.0 - 10.0),
            (HAlignment.RIGHT, VAlignment.CENTER, 1920.0 - 200.0 - 20.0, (1080.0 - 50.0) / 2.0),
            (HAlignment.CENTER, VAlignment.TOP, (1920.0 - 200.0) / 2.0, 10.0),
            (HAlignment.CENTER, VAlignment.BOTTOM, (1920.0 - 200.0) / 2.0, 1080.0 - 50.0 - 10.0),
            (HAlignment.CENTER, VAlignment.CENTER, (1920.0 - 200.0) / 2.0, (1080.0 - 50.0) / 2.0),
        ],
    )
    def test_all_alignment_combinations(self, halign, valign, expected_x, expected_y):
        """
        Check all alignment combinations
        """
        x, y = calc_draw_position(
            SCREEN_W,
            SCREEN_H,
            self.CONTENT_W,
            self.CONTENT_H,
            halign,
            valign,
            self.X_MARGIN,
            self.Y_MARGIN,
        )
        assert x == pytest.approx(expected_x)
        assert y == pytest.approx(expected_y)

    def test_top_is_near_zero_in_qt_pixel_space(self):
        """
        Check top is near zero in qt pixel space
        """
        # Qt's origin is top-left/y-down, so VAlignment.TOP should anchor near y=0,
        # the opposite of the old GL NDC convention (+1 == visual top).
        _, y = calc_draw_position(
            SCREEN_W,
            SCREEN_H,
            self.CONTENT_W,
            self.CONTENT_H,
            HAlignment.LEFT,
            VAlignment.TOP,
            self.X_MARGIN,
            self.Y_MARGIN,
        )
        assert y == pytest.approx(self.Y_MARGIN)
