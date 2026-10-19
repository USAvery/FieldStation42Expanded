import os
import re
import subprocess


CRT_DISPLAY_IDENTIFIER = 'HJW MACROSILICON 0x0002E9BD'
CRT_RESOLUTION = (640, 480)
MAX_NORMAL_RESOLUTION = (1920, 1080)
MAX_PLAYBACK_REFRESH = 60.1

_MODE_RE = re.compile(
    r'^(?P<width>\d+)x(?P<height>\d+) px,\s+'
    r'(?P<refresh>[0-9.]+) Hz(?:\s+\((?P<flags>[^)]*)\))?$'
)


def _wayland_environment():
    env = os.environ.copy()
    env.setdefault('XDG_RUNTIME_DIR', '/run/user/{}'.format(os.getuid()))
    env.setdefault('WAYLAND_DISPLAY', 'wayland-0')
    return env


def _parse_outputs(text):
    outputs = {}
    current_name = None

    for raw_line in text.splitlines():
        if raw_line and not raw_line[0].isspace():
            current_name = raw_line.split()[0]
            description = raw_line[len(current_name):].strip().strip('"')
            outputs[current_name] = {
                'enabled': False,
                'description': description,
                'modes': [],
                'current': None,
            }
            continue

        if current_name is None:
            continue

        line = raw_line.strip()

        if line == 'Enabled: yes':
            outputs[current_name]['enabled'] = True
            continue

        match = _MODE_RE.match(line)
        if not match:
            continue

        mode = (
            int(match.group('width')),
            int(match.group('height')),
            float(match.group('refresh')),
        )

        if mode not in outputs[current_name]['modes']:
            outputs[current_name]['modes'].append(mode)

        flags = match.group('flags') or ''
        if 'current' in flags:
            outputs[current_name]['current'] = mode

    return outputs


def _preferred_multiple(fps):
    if 24.5 <= fps <= 30.5:
        return 2

    return 1


def _best_refresh(fps, candidates):
    if not candidates:
        return None

    candidates = sorted(set(candidates))

    if fps is None or fps <= 0:
        # A guide/startup policy check may happen before MPV has a video FPS.
        # Prefer conventional 60 Hz without exceeding the normal playback cap.
        return min(
            candidates,
            key=lambda refresh: (
                abs(refresh - 60.0),
                -refresh,
            ),
        )

    preferred_multiple = _preferred_multiple(fps)

    def score(refresh):
        ratio = refresh / fps
        multiple = max(1, int(round(ratio)))
        cadence_error = abs(refresh - (fps * multiple)) / max(refresh, 1.0)

        return (
            cadence_error,
            abs(multiple - preferred_multiple),
            abs(refresh - (fps * preferred_multiple)),
        )

    return min(candidates, key=score)


def _target_resolution(output_data):
    modes = output_data['modes']
    description = output_data.get('description', '')

    if CRT_DISPLAY_IDENTIFIER in description:
        crt_modes = [
            mode
            for mode in modes
            if mode[0:2] == CRT_RESOLUTION
        ]

        if not crt_modes:
            return None, 'MacroSilicon CRT (640x480 unavailable)'

        return CRT_RESOLUTION, 'MacroSilicon CRT -> 640x480'

    max_width, max_height = MAX_NORMAL_RESOLUTION
    resolutions = {
        (width, height)
        for width, height, _refresh in modes
        if width <= max_width and height <= max_height
    }

    if not resolutions:
        return None, 'normal display (no mode <= 1920x1080)'

    resolution = max(
        resolutions,
        key=lambda value: (
            value[0] * value[1],
            value[0],
            value[1],
        ),
    )

    return resolution, 'normal display -> max 1920x1080'


def select_display_mode(wlr_output, fps=None):
    """Select the safest resolution and best cadence from wlr-randr output.

    The display type owns resolution policy:
      * MacroSilicon CRT adapter: 640x480.
      * Other displays: highest advertised mode at or below 1920x1080.

    The source video FPS owns refresh selection inside that resolution.
    """
    outputs = _parse_outputs(wlr_output)

    for output_name, output_data in outputs.items():
        if not output_data['enabled'] or output_data['current'] is None:
            continue

        resolution, policy = _target_resolution(output_data)
        if resolution is None:
            return None

        width, height = resolution
        refresh_candidates = [
            refresh
            for mode_width, mode_height, refresh in output_data['modes']
            if mode_width == width and mode_height == height
        ]

        normal_refreshes = [
            refresh
            for refresh in refresh_candidates
            if refresh <= MAX_PLAYBACK_REFRESH
        ]

        if normal_refreshes:
            refresh_candidates = normal_refreshes

        best_refresh = _best_refresh(fps, refresh_candidates)
        if best_refresh is None:
            return None

        return {
            'output': output_name,
            'description': output_data.get('description', ''),
            'policy': policy,
            'current': output_data['current'],
            'target': (width, height, best_refresh),
            'fps': fps,
        }

    return None


def enforce_display_resolution_policy(logger=None):
    """Enforce only the display resolution policy, preserving refresh cadence.

    This is used before loading a new video. It repairs HDMI/compositor
    fallbacks to native 4K without unnecessarily changing a valid 1080p/CRT
    refresh rate. The normal refresh matcher can then select cadence once MPV
    knows the new video's FPS.
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
            logger.debug(
                'Could not query Wayland display resolution: {}'.format(exc)
            )
        return False

    if result.returncode != 0:
        if logger:
            logger.debug(
                'wlr-randr failed while checking display resolution: {}'.format(
                    result.stderr.strip()
                )
            )
        return False

    outputs = _parse_outputs(result.stdout)

    for output_name, output_data in outputs.items():
        if not output_data['enabled'] or output_data['current'] is None:
            continue

        target_resolution, policy = _target_resolution(output_data)
        if target_resolution is None:
            return False

        current_width, current_height, current_refresh = output_data['current']
        target_width, target_height = target_resolution

        if (
            current_width == target_width
            and current_height == target_height
        ):
            return True

        candidates = [
            refresh
            for width, height, refresh in output_data['modes']
            if (
                width == target_width
                and height == target_height
                and refresh <= MAX_PLAYBACK_REFRESH
            )
        ]

        if not candidates:
            candidates = [
                refresh
                for width, height, refresh in output_data['modes']
                if width == target_width and height == target_height
            ]

        if not candidates:
            return False

        # Keep the current refresh as closely as the target resolution allows.
        # This avoids 50 -> 60 -> 50 churn during an ordinary channel change.
        target_refresh = min(
            candidates,
            key=lambda refresh: abs(refresh - current_refresh),
        )

        mode = '{}x{}@{:.6f}Hz'.format(
            target_width,
            target_height,
            target_refresh,
        )

        if logger:
            logger.info(
                'Display resolution policy [{}]: {} {}x{}@{:.3f} -> '
                '{}x{}@{:.3f}'.format(
                    policy,
                    output_name,
                    current_width,
                    current_height,
                    current_refresh,
                    target_width,
                    target_height,
                    target_refresh,
                )
            )

        try:
            change = subprocess.run(
                [
                    'wlr-randr',
                    '--output',
                    output_name,
                    '--mode',
                    mode,
                    '--scale',
                    '1',
                ],
                capture_output=True,
                text=True,
                timeout=5,
                env=_wayland_environment(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            if logger:
                logger.warning(
                    'Could not enforce display resolution: {}'.format(exc)
                )
            return False

        if change.returncode != 0:
            if logger:
                logger.warning(
                    'Could not set display resolution to {}: {}'.format(
                        mode,
                        change.stderr.strip(),
                    )
                )
            return False

        return True

    return False


def match_display_refresh_rate(fps=None, logger=None):
    """Enforce display resolution policy and match refresh to source FPS."""
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
            logger.debug('Could not query Wayland display modes: {}'.format(exc))
        return False

    if result.returncode != 0:
        if logger:
            logger.debug(
                'wlr-randr failed while querying display modes: {}'.format(
                    result.stderr.strip()
                )
            )
        return False

    selection = select_display_mode(result.stdout, fps=fps)
    if selection is None:
        if logger:
            logger.warning('Could not find a safe display mode for playback')
        return False

    current_width, current_height, current_refresh = selection['current']
    target_width, target_height, target_refresh = selection['target']

    if logger:
        logger.debug(
            'Display policy: {} [{}]'.format(
                selection['policy'],
                selection['description'],
            )
        )

    same_resolution = (
        current_width == target_width
        and current_height == target_height
    )
    same_refresh = abs(current_refresh - target_refresh) < 0.01

    if same_resolution and same_refresh:
        return True

    mode = '{}x{}@{:.6f}Hz'.format(
        target_width,
        target_height,
        target_refresh,
    )

    source_text = (
        '{:.3f} fps'.format(fps)
        if fps is not None and fps > 0
        else 'unknown FPS'
    )

    if logger:
        logger.info(
            'Display mode for {}: {} {}x{}@{:.3f} -> {}x{}@{:.3f}'.format(
                source_text,
                selection['output'],
                current_width,
                current_height,
                current_refresh,
                target_width,
                target_height,
                target_refresh,
            )
        )

    try:
        change = subprocess.run(
            [
                'wlr-randr',
                '--output',
                selection['output'],
                '--mode',
                mode,
                '--scale',
                '1',
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=_wayland_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if logger:
            logger.warning('Could not change display mode: {}'.format(exc))
        return False

    if change.returncode != 0:
        if logger:
            logger.warning(
                'Could not set display mode to {}: {}'.format(
                    mode,
                    change.stderr.strip(),
                )
            )
        return False

    return True
