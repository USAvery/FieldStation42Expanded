#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Parse XML or plain-text NFO sidecars into metadata and display fields, and launch or close eligible
metadata overlays.
"""
import os
import logging
import multiprocessing

from fs42.tools.media._constants import MAX_NFO_LINES
from fs42.tools.media._constants import OVERLAY_TYPES
from fs42.tools.media._constants import _OVERLAY_DEFAULTS
from fs42.tools.media._constants import DEFAULT_SHOW_SECONDS

_logger = logging.getLogger('NFOAgent')


class NFOData(object):
    """
    Hold the ordered text lines used by the media-information overlay
    """

    def __init__(self, lines):
        """
        Store display lines with title, information, and description in positional order
        """
        self.lines = lines  # list of non-empty strings, up to MAX_NFO_LINES

    @property
    def title(self):
        """
        Return the first display line or an empty string
        """
        return self.lines[0] if self.lines else ''

    @property
    def info(self):
        """
        Return the second display line or an empty string
        """
        return self.lines[1] if len(self.lines) > 1 else ''

    @property
    def description(self):
        """
        Return the third display line or an empty string
        """
        return self.lines[2] if len(self.lines) > 2 else ''


def _run_overlay_app(lines, play_duration, show_seconds, overlay_cfg):
    """
    Run the Qt media-information overlay with configured styling and visibility timing

    :param lines:         (lst<str>) metadata lines to display
    :param play_duration: (float) media playback length in seconds, or None for persistent display
    :param show_seconds:  (float) duration of timed visibility periods in seconds
    :param overlay_cfg:   (dict) font, text-effect, layout, and fade settings
    """

    import sys
    import signal
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWidgets import QWidget
    from PySide6.QtGui import QColor
    from PySide6.QtGui import QPainter
    from PySide6.QtGui import QFont
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtCore import Qt
    from PySide6.QtCore import QTimer

    def _qt_weight(weight_str):
        """
        Map the bold setting to Qt's bold weight and other values to normal weight
        """
        return QFont.Bold if weight_str == 'bold' else QFont.Normal

    class NFOOverlayWindow(QWidget):
        """
        Paint metadata lines on a transparent screen-sized surface with adjustable opacity
        """

        def __init__(self, nfo_lines):
            """
            Scale metadata text for the screen and load configured fonts, colors, and effects
            """
            super(NFOOverlayWindow, self).__init__()
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_NoSystemBackground)
            self.setAutoFillBackground(False)
            self.setStyleSheet('background: transparent;')
            self.setCursor(Qt.BlankCursor)

            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.geometry()
                self.setGeometry(screen_rect)
                screen_height = screen_rect.height()
            else:
                screen_height = 1080

            self.scale = screen_height / 1080.0

            if overlay_cfg['overlay_type'] == 'minimal':
                self.lines = nfo_lines[:2]
            else:
                self.lines = nfo_lines

            font_family = 'Arial'
            font_path = overlay_cfg['overlay_font_path']
            if font_path and os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        font_family = families[0]

            self.title_font = QFont(font_family, int(overlay_cfg['overlay_title_size'] * self.scale),
                                    _qt_weight(overlay_cfg['overlay_title_weight']))
            self.body_font = QFont(font_family, int(overlay_cfg['overlay_body_size'] * self.scale),
                                   _qt_weight(overlay_cfg['overlay_body_weight']))

            self.text_color = QColor(*overlay_cfg['overlay_text_color'])
            self.effect_color = QColor(*overlay_cfg['overlay_shadow_color'])
            self.opacity = 1.0

        def _draw_drop_shadow(self, painter, x, y, text, font, px):
            """
            Paint text over repeated diagonal offsets to create a shadow

            :param painter: (QPainter) active drawing context
            :param x:       (int) text baseline origin in pixels
            :param y:       (int) text baseline height in pixels
            :param text:    (str) line to paint
            :param font:    (QFont) text font
            :param px:      (int) shadow offset extent in pixels
            """
            painter.setFont(font)
            painter.setPen(self.effect_color)
            for i in range(1, px + 1):
                painter.drawText(x + i, y + i, text)
            painter.setPen(self.text_color)
            painter.drawText(x, y, text)

        def _draw_outline(self, painter, x, y, text, font, px):
            """
            Paint text at eight surrounding offsets before painting its foreground

            :param painter: (QPainter) active drawing context
            :param x:       (int) text baseline origin in pixels
            :param y:       (int) text baseline height in pixels
            :param text:    (str) line to paint
            :param font:    (QFont) text font
            :param px:      (int) outline offset in pixels
            """
            painter.setFont(font)
            offsets = [
                (-px, -px),
                (0, -px),
                (px, -px),
                (-px, 0),
                (px, 0),
                (-px, px),
                (0, px),
                (px, px),
            ]
            painter.setPen(self.effect_color)
            for dx, dy in offsets:
                painter.drawText(x + dx, y + dy, text)
            painter.setPen(self.text_color)
            painter.drawText(x, y, text)

        def _draw_text(self, painter, x, y, text, font, px):
            """
            Paint a metadata line with the configured shadow or outline effect
            """
            if overlay_cfg['overlay_effect'] == 'drop_shadow':
                self._draw_drop_shadow(painter, x, y, text, font, px)
            else:
                self._draw_outline(painter, x, y, text, font, px)

        def paintEvent(self, event):
            """
            Render metadata lines to a transparent pixmap and composite it at the current opacity
            """
            if not self.lines:
                return

            from PySide6.QtGui import QPixmap

            # Render text and effect to an off-screen pixmap at full opacity so
            # overlapping shadow copies composite correctly, then draw the whole
            # pixmap onto the widget at self.opacity so everything fades as one.
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.transparent)

            pm = QPainter(pixmap)
            pm.setRenderHint(QPainter.Antialiasing)
            pm.setRenderHint(QPainter.TextAntialiasing)

            scale = self.scale
            margin_x = int(80 * scale)
            margin_y = int(80 * scale)
            px = max(1, int(overlay_cfg['overlay_offset_px'] * scale))

            title_metrics = QFontMetrics(self.title_font)
            body_metrics = QFontMetrics(self.body_font)

            title_line_h = int(title_metrics.height() * 1.2)
            body_line_h = int(body_metrics.height() * 1.2)

            # Anchor to the bottom of the screen
            total_h = title_line_h + body_line_h * (len(self.lines) - 1)
            start_y = self.height() - margin_y - total_h

            x = margin_x
            y = start_y + title_metrics.ascent()
            self._draw_text(pm, x, y, self.lines[0], self.title_font, px)

            y += title_line_h
            for line in self.lines[1:]:
                self._draw_text(pm, x, y, line, self.body_font, px)
                y += body_line_h

            pm.end()

            painter = QPainter(self)
            painter.setOpacity(self.opacity)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()

    FADE_INTERVAL_MS = 30  # ~33 fps

    def fade_out(on_done=None):
        """
        Start a timer that fades the overlay to transparent and optionally invokes a completion callback
        """
        steps = max(1, overlay_cfg['overlay_fade_duration_ms'] // FADE_INTERVAL_MS)
        step_size = 1.0 / steps
        timer = QTimer()

        def tick():
            """
            Decrease overlay opacity for one fade step and finish at full transparency
            """
            window.opacity = max(0.0, window.opacity - step_size)
            window.update()
            if window.opacity <= 0.0:
                timer.stop()
                if on_done:
                    on_done()

        window._fade_timer = timer  # prevent GC
        timer.timeout.connect(tick)
        timer.start(FADE_INTERVAL_MS)

    def fade_in():
        """
        Show the overlay and start a timer that increases its opacity to fully visible
        """
        window.opacity = 0.0
        window.show()
        steps = max(1, overlay_cfg['overlay_fade_duration_ms'] // FADE_INTERVAL_MS)
        step_size = 1.0 / steps
        timer = QTimer()

        def tick():
            """
            Increase overlay opacity for one fade step and stop at full visibility
            """
            window.opacity = min(1.0, window.opacity + step_size)
            window.update()
            if window.opacity >= 1.0:
                timer.stop()

        window._fade_timer = timer  # prevent GC
        timer.timeout.connect(tick)
        timer.start(FADE_INTERVAL_MS)

    def signal_handler(sig, frame):
        """
        Quit the metadata overlay's Qt event loop when interrupted
        """
        QApplication.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app = QApplication(sys.argv)
    window = NFOOverlayWindow(nfo_lines=lines)
    window.show()

    # Set up show/hide timers when we know how long the clip runs.
    # Only bother if the clip is long enough to have a hidden middle section.
    if play_duration is not None and play_duration > show_seconds * 2:
        hide_timer = QTimer()
        hide_timer.setSingleShot(True)
        hide_timer.timeout.connect(lambda: fade_out(on_done=window.hide))
        hide_timer.start(int(show_seconds * 1000))

        show_timer = QTimer()
        show_timer.setSingleShot(True)
        show_timer.timeout.connect(fade_in)
        show_timer.start(int((play_duration - show_seconds) * 1000))

    sys.exit(app.exec())


def _load_overlay_config():
    """
    Merge recognized overlay settings from the station manager into display defaults
    """
    cfg = dict(_OVERLAY_DEFAULTS)
    try:
        from fs42.core.station_manager import StationManager
        main_conf = StationManager().server_conf
        overlay_conf = main_conf.get('overlay_conf', {})
        for key in _OVERLAY_DEFAULTS:
            if key in overlay_conf:
                cfg[key] = overlay_conf[key]
    except Exception as e:
        _logger.warning('Could not load overlay config from StationManager: {}'.format(e))
    return cfg


def parse_nfo_string(content):
    """
    Parse an NFO sidecar's contents into a normalized metadata dict

    Handles any Kodi-format XML root tag (musicvideo, movie,
    episodedetails, tvshow, plus a generic fallback for other tags) and a
    plain-text fallback for non-XML files. Returns a dict carrying a `type`
    discriminator, or None if nothing usable could be parsed.

    Empty string fields are dropped so the stored JSON stays tidy.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        # Not XML — fall back to plain text, one field per non-empty line.
        lines = [l.strip() for l in content.splitlines() if l.strip()][:MAX_NFO_LINES]
        if not lines:
            return None
        return {'type': 'plaintext', 'title': lines[0], 'lines': lines}

    def get(field):
        """
        Read trimmed text from a direct XML child, using an empty string when missing
        """
        el = root.find(field)
        return el.text.strip() if el is not None and el.text else ''

    def as_int(raw):
        """
        Convert digit-only metadata text to an integer and preserve other values
        """
        return int(raw) if raw.isdigit() else raw

    tag = root.tag
    if tag == 'musicvideo':
        meta = {
            'type': 'music',
            'title': get('title'),
            'artist': get('artist'),
            'album': get('album'),
            'year': get('year') or get('premiered')[:4],
            'genre': get('genre'),
        }
    elif tag == 'movie':
        meta = {
            'type': 'movie',
            'title': get('title'),
            'year': get('year') or get('premiered')[:4],
            'plot': get('plot') or get('outline'),
            'genre': get('genre'),
        }
    elif tag == 'episodedetails':
        meta = {
            'type': 'episode',
            'title': get('title'),
            'show_title': get('showtitle'),
            'season': as_int(get('season')),
            'episode': as_int(get('episode')),
            'aired': get('aired'),
            'plot': get('plot') or get('outline'),
        }
    elif tag == 'tvshow':
        meta = {
            'type': 'tvshow',
            'title': get('title'),
            'year': get('year') or get('premiered')[:4],
            'plot': get('plot') or get('outline'),
            'genre': get('genre'),
        }
    else:
        # Unknown/unsupported Kodi root tag — keep the title and any of the
        # common fields that happen to be present.
        title = get('title')
        if not title:
            return None
        meta = {'type': tag, 'title': title}
        for opt in ('year', 'plot', 'genre'):
            opt_value = get(opt)
            if opt_value:
                meta[opt] = opt_value

    # Drop empty-string fields; keep non-string values (e.g. int season).
    meta = {k: v for k, v in meta.items() if v != ''}

    # Require at least one real field beyond the type discriminator.
    return meta if len(meta) > 1 else None


def read_metadata_from_disk(file_path):
    """
    Read and parse the UTF-8 NFO sidecar beside a media file

    :param file_path: (str) media filename whose extension is replaced with .nfo
    :return:          (dict) parsed metadata, or None if the sidecar is absent, unreadable, or invalid
    """

    nfo_path = os.path.splitext(file_path)[0] + '.nfo'

    if not os.path.exists(nfo_path):
        return None

    try:
        with open(nfo_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        _logger.warning('Failed to read NFO file {0}: {1}'.format(nfo_path, e))
        return None

    meta = parse_nfo_string(content)
    if meta is None:
        _logger.warning('NFO file {} could not be parsed'.format(nfo_path))
    return meta


def overlay_lines(meta):
    """
    Select nonempty music or plaintext metadata lines for the compact overlay

    :param meta: (dict) normalized media metadata
    :return:     (list) display lines up to MAX_NFO_LINES, or None for unsupported or empty metadata
    """

    if not meta:
        return None

    meta_type = meta.get('type')
    if meta_type == 'music':
        ordered = [meta.get(k, '') for k in ('artist', 'title', 'album', 'year')]
        lines = [str(l) for l in ordered if l][:MAX_NFO_LINES]
        return lines or None
    if meta_type == 'plaintext':
        lines = [l for l in meta.get('lines', []) if l][:MAX_NFO_LINES]
        return lines or None
    return None


def display_fields(meta):
    """
    Map music, episode, movie, or plaintext metadata into three common display fields

    :param meta: (dict) normalized media metadata
    :return:     (dict) title, info, and description strings, or None if metadata is absent
    """

    if not meta:
        return None

    meta_type = meta.get('type')
    title = str(meta.get('title', ''))

    if meta_type == 'music':
        info = str(meta.get('artist', ''))
        description = str(meta.get('album', ''))
    elif meta_type == 'episode':
        info = str(meta.get('show_title', ''))
        description = str(meta.get('plot', ''))
    elif meta_type == 'plaintext':
        lines = meta.get('lines', [])
        if not title and lines:
            title = lines[0]
        info = lines[1] if len(lines) > 1 else ''
        description = lines[2] if len(lines) > 2 else ''
    else:  # movie, tvshow, generic
        info = str(meta.get('year', ''))
        description = str(meta.get('plot', ''))

    return {'title': title, 'info': info, 'description': description}


def show_overlay(nfo_data, play_duration=None, show_seconds=DEFAULT_SHOW_SECONDS):
    """
    Start a separate daemon process displaying the supplied media-information lines

    :param nfo_data:      (NFOData) display lines and title, or None to skip display
    :param play_duration: (float) media duration in seconds, or None for persistent display
    :param show_seconds:  (float) length of timed visibility periods in seconds
    :return:              (Process) started overlay process, or None if absent or startup fails
    """

    if nfo_data is None:
        return None
    try:
        overlay_cfg = _load_overlay_config()
        process = multiprocessing.Process(
            target=_run_overlay_app,
            args=(nfo_data.lines, play_duration, show_seconds, overlay_cfg),
            daemon=True,
        )
        process.start()
        _logger.info("NFO overlay started (pid={0}) '{1}'".format(process.pid, nfo_data.title) +
                     (' play_duration={0:.1f}s'.format(play_duration) if play_duration else ' permanent'))
        return process
    except Exception as e:
        _logger.error('Failed to start NFO overlay: {}'.format(e))
        return None


def close_overlay(process):
    """
    Terminate an active metadata overlay, escalating to kill if it does not exit promptly
    """

    if not process or not process.is_alive():
        return
    try:
        process.terminate()
        process.join(timeout=0.2)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.1)
        _logger.debug('NFO overlay closed')
    except Exception as e:
        _logger.warning('Error closing NFO overlay: {}'.format(e))
