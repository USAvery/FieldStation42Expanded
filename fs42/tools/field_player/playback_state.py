#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Track new-file readiness and detect stalled scheduled playback.
"""
import time
import threading


class PlaybackState(object):
    """
    Track new-file presentation readiness and request recovery when the playback clock stalls
    """
    def __init__(self, mpv):
        """
        Bind readiness events to the existing MPV connection

        :param mpv: (obj) persistent MPV client
        """
        self._loaded = threading.Event()
        self._ready = threading.Event()
        self._position = None
        self._advanced_at = None
        self._next_check = 0.0
        mpv.bind_event('file-loaded', self._on_file_loaded)
        mpv.bind_event('playback-restart', self._on_playback_restart)

    @property
    def ready(self):
        return self._ready.is_set()

    @property
    def loaded(self):
        return self._loaded.is_set()

    def begin(self):
        """
        Discard readiness and health samples from the previous file
        """
        self._loaded.clear()
        self._ready.clear()
        self._position = None
        self._advanced_at = None
        self._next_check = 0.0

    def _on_file_loaded(self, data):
        """
        Record completion of the new demuxer load
        """
        self._loaded.set()

    def _on_playback_restart(self, data):
        """
        Accept a presented playback cycle only after the new file loaded
        """
        if self._loaded.is_set():
            self._ready.set()

    def check_health(self, mpv, is_stream=False):
        """
        Return a recovery request when an active playback clock stops

        :param mpv:       (obj) persistent MPV client
        :param is_stream: (bool) whether to allow a longer network refill interval
        :return:           (str) recovery action, or None
        """
        now = time.monotonic()
        if now < self._next_check:
            return None
        self._next_check = now + 1.0
        if mpv.pause or (not is_stream and mpv.eof_reached):
            self._advanced_at = None
            return None
        position = mpv.time_pos
        if self._advanced_at is None or position != self._position:
            self._position = position
            self._advanced_at = now
            return None
        timeout = 8.0 if is_stream else 4.0
        if now - self._advanced_at < timeout:
            return None
        self._advanced_at = now
        return 'reconnect' if is_stream else 'fallback'
