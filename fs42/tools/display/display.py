#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Host the OSD and authenticated client-owned panels in one Qt event loop
"""
import os
import sys
import json
import secrets

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QTcpServer
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QHostAddress

from fs42.core import logger as project_logger

from fs42.tools.display import _constants


_logger = project_logger.setup('fs42.tools.display.display')


class DisplayService(object):
    """
    Own one OSD window and on-demand panels, removing client-owned content on disconnect
    """

    def __init__(self, state_file=None, osd_config=None, owner_token=None):
        """
        Initialize service discovery, client buffers, and panel ownership without opening windows

        :param state_file: (str) optional local discovery filename
        :param osd_config: (str) optional OSD configuration filename
        :param owner_token: (str) startup credential authorizing a player-owned lifetime
        """
        self._state_file = state_file or _constants.STATE_FILE
        self._osd_config = osd_config
        self._app = None
        self._server = None
        self._osd = None
        self._lock = None
        self._token = secrets.token_hex(32)
        self._clients = {}
        self._panels = {}
        self._signals = None
        self._owner = None
        self._owner_token = owner_token

    def _accept_clients(self):
        """
        Attach event-driven readers and disconnect cleanup to newly connected local clients
        """
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            connection.setReadBufferSize(_constants.MAX_MESSAGE_BYTES + 1)
            self._clients[connection] = bytearray()
            connection.readyRead.connect(lambda connection=connection: self._read_commands(connection))
            connection.disconnected.connect(lambda connection=connection: self._remove_client(connection))
            if connection.bytesAvailable():
                self._read_commands(connection)

    def _remove_client(self, connection):
        """
        Hide panels owned by a disconnected client and release its socket and command buffer

        :param connection: (QTcpSocket) disconnected local client
        """
        for kind, panel in list(self._panels.items()):
            if panel['owner'] is connection:
                self._hide_panel(kind)
        self._clients.pop(connection, None)
        connection.deleteLater()
        if connection is self._owner:
            self._app.quit()

    def _read_commands(self, connection):
        """
        Decode complete bounded JSON lines and acknowledge each command without blocking Qt

        :param connection: (QTcpSocket) client socket with available input
        """
        if connection not in self._clients:
            return
        buffer = self._clients[connection]
        buffer.extend(bytes(connection.readAll()))
        if len(buffer) > _constants.MAX_MESSAGE_BYTES:
            connection.disconnectFromHost()
            return
        while b'\n' in buffer:
            line, _, rest = buffer.partition(b'\n')
            buffer[:] = rest
            try:
                command = json.loads(line)
                if not isinstance(command, dict) or command.get('token') != self._token:
                    raise ValueError('Invalid display-service credentials')
                response = self._dispatch(connection, command)
            except Exception as err:
                _logger.warning('Display command failed: {}'.format(err))
                response = {'ok': False, 'error': str(err)}
            connection.write((json.dumps(response) + '\n').encode('utf-8'))

    def _find_panel(self, connection, identifier):
        """
        Find a presentation only when its identifier and owning client both match

        :param connection: (QTcpSocket) requesting client
        :param identifier: (str) unique presentation identifier
        :return:           (str) matching panel kind, or None when absent or owned by another client
        """
        for kind, panel in self._panels.items():
            if panel['owner'] is connection and panel['identifier'] == identifier:
                return kind
        return None

    def _dispatch(self, connection, command):
        """
        Apply a service or presentation command and return an acknowledgment

        :param connection: (QTcpSocket) authenticated requesting client
        :param command:    (dict) decoded operation and arguments
        :return:           (dict) operation result with an ok flag
        """
        action = command['action']
        if action == 'inspect':
            return {'ok': True, 'pid': os.getpid(), 'osd_visible': self._osd.isVisible(),
                    'osd_timer_active': self._osd.timer.isActive(),
                    'panels': {kind: {'identifier': panel['identifier'],
                                     'visible': panel['window'].isVisible(),
                                     'timer_active': panel['window']._timer.isActive(),
                                     'width': panel['window'].width(), 'height': panel['window'].height()}
                               for kind, panel in self._panels.items()}}
        if action == 'ping':
            return {'ok': True, 'pid': os.getpid()}
        if action == 'attach':
            owned = bool(self._owner_token and command.get('owner_token') == self._owner_token)
            if owned:
                self._owner = connection
            return {'ok': True, 'owned': owned}
        if action == 'show':
            return self._show_panel(connection, command)
        if action == 'shutdown':
            if connection is not self._owner:
                raise ValueError('Only the owning player can stop the display service')
            self._app.quit()
            return {'ok': True}
        kind = self._find_panel(connection, command.get('identifier'))
        if action == 'state':
            return {'ok': True, 'active': kind is not None}
        if action == 'hide':
            if kind is not None:
                self._hide_panel(kind)
            return {'ok': True}
        if action == 'update' and kind == 'parental_controls':
            self._panels[kind]['window'].apply_state(**command['values'])
            return {'ok': True}
        raise ValueError('Unknown display operation or inactive presentation: {}'.format(action))

    def _create_panel(self, kind, options):
        """
        Import and construct only the requested display so idle OSD memory stays small

        :param kind:    (str) supported presentation type
        :param options: (dict) display-constructor arguments
        :return:        (BaseDisplay) new display window
        """
        if kind == 'now_playing':
            from fs42.tools.overlay.display.now_playing_display import NowPlayingDisplay
            return NowPlayingDisplay(**options)
        if kind == 'ticker':
            from fs42.tools.overlay.display.ticker_display import TickerDisplay
            return TickerDisplay(**options)
        if kind == 'parental_controls':
            from fs42.tools.overlay.display.parental_controls_display import ParentalControlsDisplay
            return ParentalControlsDisplay(**options)
        if kind == 'media_info':
            from fs42.tools.overlay.display.media_info_display import MediaInfoDisplay
            return MediaInfoDisplay(**options)
        raise ValueError('Unknown display type: {}'.format(kind))

    def _show_panel(self, connection, command):
        """
        Replace player panels, reject overlapping tickers, and retain presentation ownership

        :param connection: (QTcpSocket) client that will own the panel
        :param command:    (dict) panel type, identifier, and constructor arguments
        :return:           (dict) acknowledgment with whether the presentation was accepted
        """
        kind = command['kind']
        if kind == 'ticker' and kind in self._panels:
            return {'ok': True, 'accepted': False}
        window = self._create_panel(kind, command['options'])
        self._hide_panel(kind)
        identifier = command['identifier']
        self._panels[kind] = {'owner': connection, 'identifier': identifier, 'window': window}
        window.finished.connect(lambda: self._finish_panel(kind, identifier))
        window.show()
        window.raise_()
        return {'ok': True, 'accepted': True}

    def _finish_panel(self, kind, identifier):
        """
        Remove a completed panel only if it has not already been replaced
        """
        panel = self._panels.get(kind)
        if panel is not None and panel['identifier'] == identifier:
            self._hide_panel(kind)

    def _hide_panel(self, kind):
        """
        Close a presentation, stop its timers, and schedule its Qt resources for deletion
        """
        panel = self._panels.pop(kind, None)
        if panel is not None:
            panel['window'].close()
            panel['window'].deleteLater()

    def _publish(self):
        """
        Atomically advertise the live socket and its private authentication token
        """
        temporary = self._state_file + '.tmp'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as f_out:
            json.dump({'port': self._server.serverPort(), 'token': self._token, 'pid': os.getpid()}, f_out)
        os.replace(temporary, self._state_file)

    def run(self):
        """
        Run one persistent Qt application, returning immediately when another service owns the lock

        :return: (int) application exit code
        """
        from fs42.tools.osd.osd import OsdWindow
        from fs42.tools.osd._api import load_objects
        os.makedirs(os.path.dirname(os.path.abspath(self._state_file)), exist_ok=True)
        self._lock = QLockFile(self._state_file + '.lock')
        self._lock.setStaleLockTime(0)
        if not self._lock.tryLock(0):
            return 0
        try:
            self._app = QApplication(sys.argv)
            self._app.setQuitOnLastWindowClosed(False)
            from fs42.tools.display._signals import SignalBridge
            self._signals = SignalBridge(self._app.quit)
            self._osd = OsdWindow(load_objects(self._osd_config), event_driven=True)
            self._server = QTcpServer()
            self._server.newConnection.connect(self._accept_clients)
            if not self._server.listen(QHostAddress.LocalHost, 0):
                raise RuntimeError(self._server.errorString())
            self._publish()
            return self._app.exec()
        finally:
            self._cleanup()

    def _cleanup(self):
        """
        Release all windows, clients, discovery state, and the service's instance lock
        """
        if self._signals is not None:
            self._signals.close()
        for kind in list(self._panels):
            self._hide_panel(kind)
        if self._server is not None:
            self._server.close()
        for connection in list(self._clients):
            connection.abort()
        if self._osd is not None:
            self._osd.close()
        try:
            os.remove(self._state_file)
        except FileNotFoundError:
            pass
        if self._lock is not None:
            self._lock.unlock()
