#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Resize and position the playback window for the guide's video preview, then restore the normal
layout when the guide closes.
"""
import os
import time
import shutil
import subprocess

from fs42.tools.field_player._constants import CRT_PREVIEW
from fs42.tools.field_player._constants import NORMAL_PREVIEW
from fs42.tools.field_player._constants import ASPECT_PROFILES
from fs42.tools.field_player.display_refresh import select_display_mode
from fs42.tools.field_player.display_refresh import CRT_DISPLAY_IDENTIFIER


def _wayland_environment():
    """
    Copy the process environment with defaults for Wayland display-control commands
    """
    env = os.environ.copy()
    env.setdefault('XDG_RUNTIME_DIR', '/run/user/{}'.format(getattr(os, 'getuid', lambda: 0)()))
    env.setdefault('WAYLAND_DISPLAY', 'wayland-0')
    return env


def _query_display_selection(logger=None):
    """
    Query wlr-randr and choose guide-preview display settings, returning None on failure
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
    Read MPV's displayed video aspect ratio, falling back to sixteen by nine
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
    Choose the supported preview layout whose aspect ratio is nearest to the video
    """
    return min(
        ASPECT_PROFILES,
        key=lambda item: abs(item[1] - aspect),
    )


def _fit_inside(box, aspect):
    """
    Fit and center video inside a preview rectangle without changing its aspect ratio

    :param box:    (dict) preview x, y, width, and height in pixels
    :param aspect: (float) source video width divided by height
    :return:       (dict) fitted rectangle and horizontal/vertical bar sizes as percentages
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




def apply_guide_preview(mpv, logger=None, box=None):
    """
    Resize and center the existing MPV Wayland surface in the guide
    """
    selection = _query_display_selection(logger=logger)
    if selection is None:
        return None

    width, height, _refresh = selection['current']
    valid_box = (box and box.get('output_width') == width and box.get('output_height') == height
                 and box.get('width', 0) > 0 and box.get('height', 0) > 0)
    if not valid_box:
        is_crt = CRT_DISPLAY_IDENTIFIER in selection.get('description', '')
        default_box = CRT_PREVIEW if is_crt else NORMAL_PREVIEW
        reference = (640, 480) if is_crt else (1920, 1080)
        box = {key: int(round(value * (float(width) / reference[0] if key in ('x', 'width')
                                      else float(height) / reference[1])))
               for key, value in default_box.items()}
    aspect = _video_aspect(mpv)
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
                'left_pct': 0.0, 'right_pct': 0.0, 'top_pct': 0.0, 'bottom_pct': 0.0,
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
        time.sleep(0.03)

        if not _trigger_labwc_geometry(geometry['x'], geometry['y'], logger=logger):
            mpv.geometry = state['geometry']
            mpv.video_margin_ratio_left = state['video_margin_ratio_left']
            mpv.video_margin_ratio_right = state['video_margin_ratio_right']
            mpv.video_margin_ratio_top = state['video_margin_ratio_top']
            mpv.video_margin_ratio_bottom = state['video_margin_ratio_bottom']
            mpv.fullscreen = state['fullscreen']
            return None

        if logger:
            logger.info('Placed native preview: aspect {:.5f}, {},{} {}x{}'.format(
                aspect, geometry['x'], geometry['y'], geometry['width'], geometry['height']))

        return state
    except Exception as exc:
        if logger:
            logger.warning(
                'Could not place MPV window in guide preview: {}'.format(exc)
            )

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


def _trigger_labwc_geometry(x, y, logger=None):
    """
    Position a client-sized window with bounded binary compositor moves

    :param x: (int) absolute horizontal position on the active output
    :param y: (int) absolute vertical position on the active output
    :return:   (bool) whether the compositor command completed
    """
    wtype = shutil.which('wtype')
    if not wtype or not (0 <= x < 4096 and 0 <= y < 4096):
        return False
    command = [wtype, '-M', 'logo', '-k', 'F20']
    for value, modifier in [(x, 'ctrl'), (y, 'shift')]:
        command.extend(['-M', modifier])
        for bit in range(12):
            if value & (1 << bit):
                command.extend(['-k', 'F{}'.format(bit + 1)])
        command.extend(['-m', modifier])
    command.extend(['-m', 'logo'])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2,
                                env=_wayland_environment(), check=False)
        if result.returncode == 0:
            return True
        if logger:
            logger.warning('Compositor geometry command failed: {}'.format(result.stderr.strip()))
    except (OSError, subprocess.SubprocessError) as exc:
        if logger:
            logger.warning('Could not position guide preview: {}'.format(exc))
    return False
