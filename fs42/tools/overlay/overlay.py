#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Run each on-demand overlay in its own Qt process and share signal handling, locking, and cleanup
"""
import os
import sys
import signal
import tempfile
import multiprocessing

from PySide6.QtCore import QTimer
from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from fs42.core import logger as project_logger

from fs42.tools.overlay._utils import OverlayError
from fs42.tools.overlay._constants import TICKER_LOCK_KEY
from fs42.tools.overlay._constants import SIGNAL_POLL_INTERVAL_MS
from fs42.tools.overlay.display.ticker_display import TickerDisplay
from fs42.tools.overlay.display.now_playing_display import NowPlayingDisplay
from fs42.tools.overlay.display.parental_controls_display import ParentalControlsDisplay


_logger = project_logger.setup('fs42.tools.overlay.overlay')


_DISPLAY_TYPES = {'now_playing': NowPlayingDisplay,
                  'ticker': TickerDisplay,
                  'parental_controls': ParentalControlsDisplay}


class Overlay(object):
    """
    Own the application, window, and child-process lifecycle for one on-demand overlay
    """

    def __init__(self, overlay_type, **options):
        """
        Select a display and retain the inputs needed to create it inside its child process

        :param overlay_type: (str) now_playing, ticker, or parental_controls
        :param options:      (dict) keyword arguments forwarded to the selected display
        """
        self._overlay_type = overlay_type
        self._options = options
        self._app = None
        self._window = None
        self._lock = None
        self._signal_timer = None
        self._signal_handlers = {}
        self._check_args()

    def _check_args(self):
        """
        Reject unknown overlay types before creating a Qt application or child process
        """
        if self._overlay_type not in _DISPLAY_TYPES:
            msg = 'Unknown overlay type: {}'.format(self._overlay_type)
            raise OverlayError(msg)

    def _acquire_lock(self):
        """
        Allow one ticker process at a time while leaving other overlay lifetimes independent

        :return: (bool) whether this overlay may start
        """
        if self._overlay_type != 'ticker':
            return True
        path = os.path.join(tempfile.gettempdir(), '{}.lock'.format(TICKER_LOCK_KEY))
        self._lock = QLockFile(path)
        self._lock.setStaleLockTime(0)
        if self._lock.tryLock(0):
            return True
        _logger.info('Ticker is already running or its lock is unavailable')
        return False

    def _quit(self, signum, frame):
        """
        Request event-loop shutdown when the overlay process receives an interrupt or termination

        :param signum: (int) received operating-system signal
        :param frame:  (frame) interrupted Python stack frame
        """
        if self._app is not None:
            self._app.quit()

    def _setup_signals(self):
        """
        Register shutdown signals and keep Python responsive while Qt owns the event loop
        """
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._signal_handlers[signum] = signal.signal(signum, self._quit)
        self._signal_timer = QTimer()
        self._signal_timer.timeout.connect(self._poll_signals)
        self._signal_timer.start(SIGNAL_POLL_INTERVAL_MS)

    def _poll_signals(self):
        """
        Return control to Python periodically so pending signal handlers can run
        """
        pass

    def _cleanup(self):
        """
        Close the display, stop signal polling, restore handlers, and release the ticker lock
        """
        if self._window is not None:
            self._window.close()
        if self._signal_timer is not None:
            self._signal_timer.stop()
        for signum, handler in self._signal_handlers.items():
            signal.signal(signum, handler)
        self._signal_handlers.clear()
        if self._lock is not None:
            self._lock.unlock()

    def run(self):
        """
        Show the selected display and run Qt until it finishes or its process is interrupted

        :return: (int) Qt exit code, or one when an existing ticker prevents startup
        """
        try:
            # Claim the ticker lock before opening its window
            if not self._acquire_lock():
                return 1

            # Build the display inside the process that owns its Qt event loop
            self._app = QApplication(sys.argv)
            self._window = _DISPLAY_TYPES[self._overlay_type](**self._options)
            self._window.finished.connect(self._app.quit)
            self._setup_signals()
            self._window.show()
            self._window.raise_()
            return self._app.exec()
        finally:
            self._cleanup()

    def start(self):
        """
        Launch this overlay in a child process without creating Qt objects in the caller

        :return: (Process) started process whose lifetime the player can manage
        """
        process = multiprocessing.Process(target=run_overlay, args=(self._overlay_type, self._options))
        process.start()
        return process


def run_overlay(overlay_type, options):
    """
    Construct and run an overlay as an importable multiprocessing entry point

    :param overlay_type: (str) registered display type
    :param options:      (dict) constructor arguments for that display
    """
    sys.exit(Overlay(overlay_type, **options).run())
