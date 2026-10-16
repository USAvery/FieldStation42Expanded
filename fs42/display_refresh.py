import os
import re
import subprocess


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
            outputs[current_name] = {
                'enabled': False,
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


def match_display_refresh_rate(fps, logger=None):
    if fps is None or fps <= 0:
        return False

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

    outputs = _parse_outputs(result.stdout)

    active_name = None
    active_data = None

    for output_name, output_data in outputs.items():
        if output_data['enabled'] and output_data['current'] is not None:
            active_name = output_name
            active_data = output_data
            break

    if active_data is None:
        if logger:
            logger.debug('No active Wayland output found for refresh matching')
        return False

    width, height, current_refresh = active_data['current']

    candidates = [
        refresh
        for mode_width, mode_height, refresh in active_data['modes']
        if mode_width == width and mode_height == height
    ]

    # Avoid unnecessary high-refresh monitor modes for TV playback.
    normal_candidates = [
        refresh for refresh in candidates
        if refresh <= 60.1
    ]
    if normal_candidates:
        candidates = normal_candidates

    best_refresh = _best_refresh(fps, candidates)
    if best_refresh is None:
        return False

    # EDIDs frequently expose 59.94 as 59.939999. Treat tiny differences as
    # already matched so we do not trigger needless HDMI mode changes.
    if abs(best_refresh - current_refresh) < 0.01:
        return True

    mode = '{}x{}@{:.6f}Hz'.format(width, height, best_refresh)

    if logger:
        logger.info(
            'Matching display refresh for {:.3f} fps: {} {:.3f} Hz -> {:.3f} Hz'.format(
                fps,
                active_name,
                current_refresh,
                best_refresh,
            )
        )

    try:
        change = subprocess.run(
            ['wlr-randr', '--output', active_name, '--mode', mode],
            capture_output=True,
            text=True,
            timeout=5,
            env=_wayland_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if logger:
            logger.warning('Could not change display refresh: {}'.format(exc))
        return False

    if change.returncode != 0:
        if logger:
            logger.warning(
                'Could not set display refresh to {}: {}'.format(
                    mode,
                    change.stderr.strip(),
                )
            )
        return False

    return True
