import os
import shutil
import subprocess
import time

from fs42.display_refresh import CRT_DISPLAY_IDENTIFIER, select_display_mode


CRT_PREVIEW_KEY = 'F10'
NORMAL_PREVIEW_KEY = 'F11'

CRT_PREVIEW = {
    'x': 375,
    'y': 0,
    'width': 265,
    'height': 194,
}
NORMAL_PREVIEW = {
    'x': 1125,
    'y': 0,
    'width': 795,
    'height': 436,
}


def _wayland_environment():
    env = os.environ.copy()
    env.setdefault('XDG_RUNTIME_DIR', '/run/user/{}'.format(os.getuid()))
    env.setdefault('WAYLAND_DISPLAY', 'wayland-0')
    return env


def _query_display_selection(logger=None):
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
            logger.warning(
                'Could not query display for guide preview: {}'.format(exc)
            )
        return None

    if result.returncode != 0:
        if logger:
            logger.warning(
                'Could not query display for guide preview: {}'.format(
                    result.stderr.strip()
                )
            )
        return None

    return select_display_mode(result.stdout)


def _trigger_labwc_preview(key_name, logger=None):
    wtype = shutil.which('wtype')
    if not wtype:
        if logger:
            logger.warning(
                'wtype is not installed; cannot resize the MPV Wayland window '
                'for the guide preview'
            )
        return False

    command = [
        wtype,
        '-M', 'logo',
        '-k', key_name,
        '-m', 'logo',
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
            logger.warning(
                'Could not trigger labwc guide preview action: {}'.format(exc)
            )
        return False

    if result.returncode != 0:
        if logger:
            logger.warning(
                'labwc guide preview action failed: {}'.format(
                    result.stderr.strip()
                )
            )
        return False

    return True


def apply_guide_preview(mpv, logger=None):
    """Resize the existing MPV Wayland surface into the guide preview."""
    selection = _query_display_selection(logger=logger)
    if selection is None:
        return None

    description = selection.get('description', '')
    is_crt = CRT_DISPLAY_IDENTIFIER in description
    key_name = CRT_PREVIEW_KEY if is_crt else NORMAL_PREVIEW_KEY
    geometry = CRT_PREVIEW if is_crt else NORMAL_PREVIEW

    try:
        state = {
            'fullscreen': bool(mpv.fullscreen),
            'video_margin_ratio_left': mpv.video_margin_ratio_left,
            'video_margin_ratio_right': mpv.video_margin_ratio_right,
            'video_margin_ratio_top': mpv.video_margin_ratio_top,
            'video_margin_ratio_bottom': mpv.video_margin_ratio_bottom,
        }

        mpv.video_margin_ratio_left = 0.0
        mpv.video_margin_ratio_right = 0.0
        mpv.video_margin_ratio_top = 0.0
        mpv.video_margin_ratio_bottom = 0.0

        mpv.fullscreen = False
        time.sleep(0.05)

        if not _trigger_labwc_preview(key_name, logger=logger):
            mpv.video_margin_ratio_left = state['video_margin_ratio_left']
            mpv.video_margin_ratio_right = state['video_margin_ratio_right']
            mpv.video_margin_ratio_top = state['video_margin_ratio_top']
            mpv.video_margin_ratio_bottom = state['video_margin_ratio_bottom']
            mpv.fullscreen = state['fullscreen']
            return None

        if logger:
            logger.info(
                'Placed MPV window in {} guide preview at {},{} {}x{}'.format(
                    'CRT' if is_crt else '1080p',
                    geometry['x'],
                    geometry['y'],
                    geometry['width'],
                    geometry['height'],
                )
            )

        return state
    except Exception as exc:
        if logger:
            logger.warning(
                'Could not place MPV window in guide preview: {}'.format(exc)
            )

        try:
            if 'state' in locals():
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
    """Restore the same MPV Wayland surface after closing the guide."""
    if state is None:
        return

    try:
        mpv.video_margin_ratio_left = state['video_margin_ratio_left']
        mpv.video_margin_ratio_right = state['video_margin_ratio_right']
        mpv.video_margin_ratio_top = state['video_margin_ratio_top']
        mpv.video_margin_ratio_bottom = state['video_margin_ratio_bottom']
        mpv.fullscreen = state['fullscreen']

        if logger:
            logger.info('Restored MPV window after guide preview')
    except Exception as exc:
        if logger:
            logger.warning(
                'Could not restore MPV window after guide preview: {}'.format(
                    exc
                )
            )
