#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Show audio metadata in a separate Qt now-playing window. Keep the window running until the player
terminates or replaces its process.
"""
import os
import sys
import signal
import tempfile
import multiprocessing

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QFontMetrics
from PySide6.QtGui import QLinearGradient
from PySide6.QtWidgets import QApplication

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.overlay.now_playing')


class SingleApplication(QApplication):
    """
    Track an existing overlay process through a temporary PID file
    """

    def __init__(self, argv, key):
        """
        Check a keyed PID file and claim it when no live process is recorded

        :param argv: (list) command-line arguments forwarded to QApplication
        :param key:  (str) identifier used to name the temporary lock file
        """
        super(SingleApplication, self).__init__(argv)

        self.lock_file = os.path.join(tempfile.gettempdir(), '{}.lock'.format(key))
        self._running = False

        # Check if lock file exists and if the process is actually running
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read().strip())

                # Check if process is actually running
                try:
                    os.kill(pid, 0)  # Doesn't kill, just checks if process exists
                    self._running = True
                except (OSError, ProcessLookupError):
                    # Process doesn't exist, remove stale lock file
                    os.remove(self.lock_file)
                    self._running = False
            except (ValueError, FileNotFoundError):
                # Invalid lock file, remove it
                try:
                    os.remove(self.lock_file)
                except FileNotFoundError:
                    pass
                self._running = False

        if not self._running:
            # Create lock file with current PID
            try:
                with open(self.lock_file, 'w') as f:
                    f.write(str(os.getpid()))
            except IOError:
                raise RuntimeError('Unable to create lock file: {}'.format(self.lock_file))

    def is_running(self):
        """
        Report whether initialization found another live process holding the overlay lock
        """
        return self._running

    def __del__(self):
        """
        Remove this application's PID file when it owns the overlay lock
        """
        # Clean up lock file on exit
        if hasattr(self, 'lock_file') and not self._running:
            try:
                os.remove(self.lock_file)
            except FileNotFoundError:
                pass


class NowPlayingWindow(QWidget):
    """
    Show title, artist, and album metadata in a persistent transparent overlay
    """

    def __init__(self, file_path, db_path, parent=None):
        """
        Load media metadata and size the now-playing panel for the primary screen

        :param file_path: (str) playing media path used for metadata lookup
        :param db_path:   (str) metadata database filename
        :param parent:    (QWidget) optional Qt parent window
        """
        super(NowPlayingWindow, self).__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.BlankCursor)  # Hide the mouse cursor

        # Make it fullscreen and get screen dimensions
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.geometry()
            self.setGeometry(screen_rect)
            screen_height = screen_rect.height()
        else:
            screen_height = 1080  # Default fallback

        # Scale fonts based on screen height
        # Base sizes are for 1080p screens
        # For 4K (2160p), fonts will be 2x larger
        # For smaller screens (720p), fonts will be proportionally smaller
        scale_factor = screen_height / 1080.0

        title_size = int(28 * scale_factor)
        info_size = int(20 * scale_factor)

        # Now Playing display dimensions - scaled for screen size
        self.box_width = int(500 * scale_factor)
        self.box_height = int(160 * scale_factor)
        self.margin_x = int(80 * scale_factor)  # More margin from left edge
        self.margin_y = int(80 * scale_factor)  # More margin from bottom edge
        self.padding = int(20 * scale_factor)

        # Colors - dark semi-transparent background with white text
        self.background_start = QColor(0, 0, 0, 200)  # Black with transparency
        self.background_end = QColor(20, 20, 20, 180)  # Slightly lighter black
        self.text_color = QColor(255, 255, 255)  # White text
        self.text_shadow = QColor(0, 0, 0, 200)  # Strong shadow for readability

        # Fonts - scaled for screen resolution
        self.title_font = QFont('Arial', title_size, QFont.Bold)
        self.info_font = QFont('Arial', info_size, QFont.Normal)

        # Store scale factor for use in paintEvent
        self.scale_factor = scale_factor

        # Get metadata from database
        self.metadata = self._get_metadata(file_path, db_path)

    def _get_metadata(self, file_path, db_path):
        """
        Read cached audio metadata via the shared MetadataIO
        """
        from fs42.tools.media import metadata_io

        meta = metadata_io.read(file_path, db_path)
        if meta:
            return {
                'title': meta.get('title', 'Unknown Track'),
                'artist': meta.get('artist', ''),
                'album': meta.get('album', ''),
                'year': meta.get('year', ''),
                'genre': meta.get('genre', '')
            }

        # Fallback to filename
        return {
            'title': os.path.splitext(os.path.basename(file_path))[0],
            'artist': '',
            'album': '',
            'year': '',
            'genre': ''
        }

    def paintEvent(self, event):
        """
        Paint the now-playing metadata over a shaded panel near the lower screen edge

        :param event: (QPaintEvent) Qt repaint notification
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Calculate text widths to determine box width
        title_metrics = QFontMetrics(self.title_font)
        info_metrics = QFontMetrics(self.info_font)

        max_text_width = title_metrics.horizontalAdvance(self.metadata['title'])
        if self.metadata['artist']:
            max_text_width = max(max_text_width, info_metrics.horizontalAdvance(self.metadata['artist']))
        if self.metadata['album']:
            max_text_width = max(max_text_width, info_metrics.horizontalAdvance(self.metadata['album']))

        # Add padding and fade zone to width
        fade_width = int(100 * self.scale_factor)  # Width of fade gradient
        actual_box_width = max(self.box_width, max_text_width + self.padding * 2 + fade_width)

        # Calculate lower left position with increased margins
        box_x = self.margin_x
        box_y = self.height() - self.box_height - self.margin_y
        box_rect = QRect(box_x, box_y, actual_box_width, self.box_height)

        # Draw background with horizontal fade gradient
        # Create a horizontal gradient that fades to transparent on the right
        gradient = QLinearGradient(box_rect.left(), 0, box_rect.right(), 0)

        # Solid background for most of the box
        gradient.setColorAt(0.0, self.background_start)
        gradient.setColorAt(0.7, self.background_end)
        # Fade to transparent on the right edge
        fade_start = QColor(self.background_end)
        fade_start.setAlpha(180)
        gradient.setColorAt(0.85, fade_start)

        fade_end = QColor(self.background_end)
        fade_end.setAlpha(0)
        gradient.setColorAt(1.0, fade_end)

        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(box_rect, 8, 8)

        # Draw text content with scaled positioning
        text_x = box_x + self.padding
        text_y = box_y + self.padding
        line_height = int(40 * self.scale_factor)
        shadow_offset = int(2 * self.scale_factor)

        # Calculate baseline offsets based on font size
        title_baseline = int(28 * self.scale_factor)
        info_baseline = int(20 * self.scale_factor)

        # Title (song name) - larger, bold
        painter.setFont(self.title_font)

        # Draw shadow for title
        painter.setPen(self.text_shadow)
        painter.drawText(text_x + shadow_offset, text_y + shadow_offset + title_baseline, self.metadata['title'])

        # Draw title
        painter.setPen(self.text_color)
        painter.drawText(text_x, text_y + title_baseline, self.metadata['title'])

        # Artist and Album - smaller, normal weight
        painter.setFont(self.info_font)
        text_y += line_height

        # Draw artist if available
        if self.metadata['artist']:
            # Shadow
            painter.setPen(self.text_shadow)
            painter.drawText(text_x + shadow_offset, text_y + shadow_offset + info_baseline,
                             self.metadata['artist'])
            # Text
            painter.setPen(self.text_color)
            painter.drawText(text_x, text_y + info_baseline, self.metadata['artist'])
            text_y += line_height

        # Draw album if available
        if self.metadata['album']:
            # Shadow
            painter.setPen(self.text_shadow)
            painter.drawText(text_x + shadow_offset, text_y + shadow_offset + info_baseline,
                             self.metadata['album'])
            # Text
            painter.setPen(self.text_color)
            painter.drawText(text_x, text_y + info_baseline, self.metadata['album'])

        painter.end()


def signal_handler(sig, frame):
    """
    Request a clean Qt event-loop exit when the overlay receives an interrupt signal
    """
    _logger.info("\nShutting down now playing overlay...")
    QApplication.quit()


def run_now_playing_app(file_path, db_path):
    """
    Run the now playing overlay application
    """

    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # Use regular QApplication - process lifecycle is managed by station_player
    app = QApplication(sys.argv)

    window = NowPlayingWindow(file_path, db_path)
    window.show()

    sys.exit(app.exec())


def run_now_playing(file_path, db_path):
    """
    Start the now playing overlay in a separate process
    """

    def now_playing_process():
        """
        Run the now-playing Qt application inside the spawned overlay process
        """
        run_now_playing_app(file_path, db_path)

    process = multiprocessing.Process(target=now_playing_process)
    process.start()
    return process


if __name__ == '__main__':
    # Example usage when run directly
    if len(sys.argv) > 2:
        run_now_playing_app(sys.argv[1], sys.argv[2])
    else:
        _logger.info('Usage: python now_playing.py <file_path> <db_path>')
        _logger.info('Example: python now_playing.py /path/to/song.mp3 runtime/fs42_fluid.db')
