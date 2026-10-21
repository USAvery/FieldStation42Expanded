#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Repair HDMI mode resets without blocking the guide or playback input loop.
"""
import logging
import threading

from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import QObject

from fs42.display_refresh import match_display_refresh_rate
from fs42.display_refresh import enforce_display_resolution_policy


class DisplayGuard(QObject):
    _finished = Signal(bool)

    def __init__(self, app, notify):
        """
        Observe screen changes and coalesce checks in one idle background worker
        """
        super(DisplayGuard, self).__init__(app)
        self._app = app
        self._notify = notify
        self._fps = None
        self._attempts = 0
        self._screens = set()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._logger = logging.getLogger('DisplayGuard')
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._enforce)
        self._finished.connect(self._on_finished)
        app.screenAdded.connect(self._connect_screen)
        app.screenRemoved.connect(self._queue_check)
        app.aboutToQuit.connect(self._stop)
        self._thread = threading.Thread(target=self._run, name='fs42-display', daemon=True)
        self._thread.start()
        for screen in app.screens():
            self._connect_screen(screen)

    def set_fps(self, fps):
        """
        Store the source cadence selected by the persistent player
        """
        self._fps = fps

    def _connect_screen(self, screen):
        """
        Subscribe once to each output's geometry and refresh notifications
        """
        if screen not in self._screens:
            self._screens.add(screen)
            screen.geometryChanged.connect(self._queue_check)
            screen.refreshRateChanged.connect(self._queue_check)
            screen.destroyed.connect(lambda: self._screens.discard(screen))
        self._queue_check()

    def _queue_check(self, *args):
        """
        Coalesce HDMI reconfiguration events before querying the compositor
        """
        self._attempts = 0
        self._debounce.start(125)

    def _on_mode_changed(self):
        """
        Ask the player to reopen audio after an actual HDMI clock change
        """
        self._notify({'type': 'audio_reload'})

    def _enforce(self):
        """
        Wake the worker without running compositor commands on the Qt thread
        """
        self._wake.set()

    def _on_finished(self, success):
        """
        Retry transient HDMI enumeration failures after the output settles
        """
        if not success and self._attempts < 8:
            self._attempts += 1
            self._debounce.start(250)

    def _stop(self):
        """
        Release the background wait when the renderer exits
        """
        self._stopped.set()
        self._wake.set()

    def _run(self):
        """
        Apply event-driven checks and a five-second reconciliation safety check
        """
        while not self._stopped.is_set():
            self._wake.wait(5.0)
            self._wake.clear()
            if self._stopped.is_set():
                return
            fps = self._fps
            if fps and fps > 0:
                success = match_display_refresh_rate(fps, logger=self._logger,
                                                     on_mode_change=self._on_mode_changed)
            else:
                success = enforce_display_resolution_policy(logger=self._logger,
                                                             on_mode_change=self._on_mode_changed)
            self._finished.emit(success)
