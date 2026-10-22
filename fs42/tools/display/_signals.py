#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Integrate operating-system shutdown signals into Qt without waking an idle display
"""
import signal
import socket

from PySide6.QtCore import QSocketNotifier


class SignalBridge(object):
    """
    Wake Qt on process-shutdown signals without a periodic Python polling timer
    """

    def __init__(self, callback):
        """
        Install a socket-backed signal wakeup and retain handlers for later restoration

        :param callback: (callable) function invoked when an interrupt or termination signal arrives
        """
        self._callback = callback
        self._reader, self._writer = socket.socketpair()
        self._reader.setblocking(False)
        self._writer.setblocking(False)
        self._previous_fd = signal.set_wakeup_fd(self._writer.fileno())
        self._handlers = {}
        self._notifier = QSocketNotifier(self._reader.fileno(), QSocketNotifier.Read)
        self._notifier.activated.connect(self._dispatch)
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._handlers[signum] = signal.signal(signum, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """
        Leave shutdown to the socket notification written by Python's signal wakeup mechanism
        """
        pass

    def _dispatch(self, *args):
        """
        Drain pending signal bytes and request application shutdown inside Qt's event loop
        """
        try:
            self._reader.recv(4096)
        except BlockingIOError:
            return
        self._callback()

    def close(self):
        """
        Disable wakeups, restore the previous signal configuration, and close both sockets
        """
        self._notifier.setEnabled(False)
        signal.set_wakeup_fd(self._previous_fd)
        for signum, handler in self._handlers.items():
            signal.signal(signum, handler)
        self._reader.close()
        self._writer.close()
