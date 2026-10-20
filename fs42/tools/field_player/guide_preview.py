#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage guide preview
"""
import os
import time
import shutil
import subprocess

from fs42.tools.field_player._constants import CRT_PREVIEW
from fs42.tools.field_player._constants import PREVIEW_KEYS
from fs42.tools.field_player._constants import NORMAL_PREVIEW
from fs42.tools.field_player._constants import ASPECT_PROFILES
from fs42.tools.field_player.display_refresh import select_display_mode
from fs42.tools.field_player.display_refresh import CRT_DISPLAY_IDENTIFIER


def _wayland_environment():
    """
    Wayland environment
    """
    env = os.environ.copy()
    env.setdefault('XDG_RUNTIME_DIR', '/run/user/{}'.format(os.getuid()))
    env.setdefault('WAYLAND_DISPLAY', 'wayland-0')
    return env


def _query_display_selection(logger=None):
    """
    Query display selection
    """
    try:
        result = subprocess.run(
            ['wlr-randr'],
            capture_output=True,
            text=True,
            timeout=3,
            env=_wayland_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if logger:
            logger.warning('Could not query display for guide preview: {}'.format(exc))
        return None

    if result.returncode != 0:
        if logger:
            logger.warning('Could not query display for guide preview: {}'.format(result.stderr.strip()))
        return None

    return select_display_mode(result.stdout)


def _video_aspect(mpv):
    """
    Video aspect
    """
    try:
        params = mpv.video_out_params or {}
    except Exception:
        params = {}

    aspect = params.get('aspect')
    if aspect and aspect > 0:
        return float(aspect)

    width = params.get('dw') or params.get('w')
    height = params.get('dh') or params.get('h')

    if width and height:
        return float(width) / float(height)

    return 16.0 / 9.0


def _closest_aspect_profile(aspect):
    """
    Closest aspect profile
    """
    return min(
        ASPECT_PROFILES,
        key=lambda item: abs(item[1] - aspect),
    )


def _fit_inside(box, aspect):
    """
    Fit inside
    """
    box_width = box['width']
    box_height = box['height']
    box_aspect = float(box_width) / float(box_height)

    if aspect >= box_aspect:
        width = box_width
        height = max(1, int(round(float(width) / aspect)))
    else:
        height = box_height
        width = max(1, int(round(float(height) * aspect)))

    x = box['x'] + int(round((box_width - width) / 2.0))
    y = box['y'] + int(round((box_height - height) / 2.0))

    bar_x = max(0.0, (box_width - width) / (2.0 * box_width) * 100.0)
    bar_y = max(0.0, (box_height - height) / (2.0 * box_height) * 100.0)

    return {
        'x': x,
        'y': y,
        'width': width,
        'height': height,
        'bar_x_percent': bar_x,
        'bar_y_percent': bar_y,
    }


def _trigger_labwc_preview(key_name, logger=None):
    """
    Trigger labwc preview
    """
    wtype = shutil.which('wtype')
    if not wtype:
        if logger:
            logger.warning('wtype is not installed; cannot resize the MPV Wayland window '
                           'for the guide preview')
        return False

    command = [
        wtype,
        '-M',
        'logo',
        '-k',
        key_name,
        '-m',
        'logo',
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=2,
            env=_wayland_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if logger:
            logger.warning('Could not trigger labwc guide preview action: {}'.format(exc))
        return False

    if result.returncode != 0:
        if logger:
            logger.warning('labwc guide preview action failed: {}'.format(result.stderr.strip()))
        return False

    return True


def apply_guide_preview(mpv, logger=None):
    """
    Resize and center the existing MPV Wayland surface in the guide
    """
    selection = _query_display_selection(logger=logger)
    if selection is None:
        return None

    description = selection.get('description', '')
    is_crt = CRT_DISPLAY_IDENTIFIER in description
    display_type = 'crt' if is_crt else 'normal'
    box = CRT_PREVIEW if is_crt else NORMAL_PREVIEW

    aspect = _video_aspect(mpv)
    profile_name, profile_aspect = _closest_aspect_profile(aspect)
    key_name = PREVIEW_KEYS[(display_type, profile_name)]
    geometry = _fit_inside(box, aspect)

    try:
        state = {
            'fullscreen': bool(mpv.fullscreen),
            'geometry': mpv.geometry,
            'video_margin_ratio_left': mpv.video_margin_ratio_left,
            'video_margin_ratio_right': mpv.video_margin_ratio_right,
            'video_margin_ratio_top': mpv.video_margin_ratio_top,
            'video_margin_ratio_bottom': mpv.video_margin_ratio_bottom,
            'preview_geometry': {
                'left_pct': geometry['bar_x_percent'],
                'right_pct': geometry['bar_x_percent'],
                'top_pct': geometry['bar_y_percent'],
                'bottom_pct': geometry['bar_y_percent'],
            },
        }

        mpv.video_margin_ratio_left = 0.0
        mpv.video_margin_ratio_right = 0.0
        mpv.video_margin_ratio_top = 0.0
        mpv.video_margin_ratio_bottom = 0.0

        # Ask MPV for the exact source-aspect size. Wayland ignores the x/y
        # portion of client geometry, so labwc supplies the absolute placement.
        mpv.geometry = '{}x{}'.format(
            geometry['width'],
            geometry['height'],
        )
        mpv.fullscreen = False
        time.sleep(0.05)

        if not _trigger_labwc_preview(key_name, logger=logger):
            mpv.geometry = state['geometry']
            mpv.video_margin_ratio_left = state['video_margin_ratio_left']
            mpv.video_margin_ratio_right = state['video_margin_ratio_right']
            mpv.video_margin_ratio_top = state['video_margin_ratio_top']
            mpv.video_margin_ratio_bottom = state['video_margin_ratio_bottom']
            mpv.fullscreen = state['fullscreen']
            return None

        if logger:
            logger.info('Placed MPV window in {} guide preview: source aspect {:.3f}, '
                        'profile {} ({:.3f}), target {},{} {}x{}'.format(
                            'CRT' if is_crt else '1080p',
                            aspect,
                            profile_name,
                            profile_aspect,
                            geometry['x'],
                            geometry['y'],
                            geometry['width'],
                            geometry['height'],
                        ))

        return state
    except Exception as exc:
        if logger:
            logger.warning('Could not place MPV window in guide preview: {}'.format(exc))

        try:
            if 'state' in locals():
                mpv.geometry = state['geometry']
                mpv.video_margin_ratio_left = state['video_margin_ratio_left']
                mpv.video_margin_ratio_right = state['video_margin_ratio_right']
                mpv.video_margin_ratio_top = state['video_margin_ratio_top']
                mpv.video_margin_ratio_bottom = state['video_margin_ratio_bottom']
                mpv.fullscreen = state['fullscreen']
            else:
                mpv.fullscreen = True
        except Exception:
            pass

        return None


def restore_guide_preview(mpv, state, logger=None):
    """
    Restore the same MPV Wayland surface after closing the guide
    """
    if state is None:
        return

    try:
        mpv.geometry = state['geometry']
        mpv.video_margin_ratio_left = state['video_margin_ratio_left']
        mpv.video_margin_ratio_right = state['video_margin_ratio_right']
        mpv.video_margin_ratio_top = state['video_margin_ratio_top']
        mpv.video_margin_ratio_bottom = state['video_margin_ratio_bottom']
        mpv.fullscreen = state['fullscreen']

        if logger:
            logger.info('Restored MPV window after guide preview')
    except Exception as exc:
        if logger:
            logger.warning('Could not restore MPV window after guide preview: {}'.format(exc))
