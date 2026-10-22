#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Send display commands without importing Qt into the playback process and track individual panels
"""
import os
import sys
import json
import time
import uuid
import socket
import threading
import subprocess

from fs42.core.paths import PROJECT_ROOT

from fs42.tools.display import _constants


class DisplayError(Exception):
    pass


class DisplayClient(object):
    """
    Keep one authenticated local connection and optionally own the shared display subprocess
    """

    def __init__(self, state_file=None, osd_config=None):
        """
        Initialize discovery and connection state without starting a display process

        :param state_file: (str) optional service-discovery filename for an isolated installation
        :param osd_config: (str) optional OSD configuration passed when starting a new service
        """
        self._state_file = state_file or _constants.STATE_FILE
        self._osd_config = osd_config
        self._socket = None
        self._reader = None
        self._token = None
        self._process = None
        self._start_token = None
        self._owns_service = False
        self._pid = None
        self._lock = threading.RLock()

    @property
    def pid(self):
        return self._pid

    def _connect(self):
        """
        Open the advertised loopback socket and verify its service token with a ping
        """
        with open(self._state_file, 'r') as f_in:
            state = json.load(f_in)
        connection = socket.create_connection((_constants.HOST, int(state['port'])),
                                              timeout=_constants.REQUEST_TIMEOUT)
        self._socket = connection
        self._reader = connection.makefile('rb')
        self._token = state['token']
        self._pid = state['pid']
        self.request('ping')
        if self._start_token is not None:
            self._owns_service = self.request('attach', owner_token=self._start_token)['owned']

    def connect(self, start=True):
        """
        Reuse an existing service or start one minimal Qt subprocess and wait for readiness

        :param start: (bool) whether to start a service when discovery or connection fails
        :return:      (DisplayClient) connected client
        """
        with self._lock:
            if self._socket is not None:
                return self
            try:
                self._connect()
                return self
            except (OSError, ValueError, KeyError, DisplayError):
                self._disconnect()
            if not start:
                raise DisplayError('The display service is not running')
            self._start_token = uuid.uuid4().hex
            command = [sys.executable, '-m', 'fs42.tools.display.main', '--state-file', self._state_file,
                       '--owner-token', self._start_token]
            if self._osd_config is not None:
                command.extend(['--osd-config', self._osd_config])
            os.makedirs(os.path.dirname(os.path.abspath(self._state_file)), exist_ok=True)
            with open(self._state_file + '.log', 'a') as log:
                self._process = subprocess.Popen(command, cwd=PROJECT_ROOT, stdin=subprocess.DEVNULL,
                                                 stdout=log, stderr=log)
            deadline = time.monotonic() + _constants.START_TIMEOUT
            while time.monotonic() < deadline:
                try:
                    self._connect()
                    return self
                except (OSError, ValueError, KeyError, DisplayError):
                    self._disconnect()
                if self._process.poll() not in (None, 0):
                    break
                time.sleep(_constants.RETRY_INTERVAL)
            self.close()
            raise DisplayError('The display service did not become ready')

    def request(self, action, **values):
        """
        Send one bounded JSON command and return its acknowledged response

        :param action: (str) service operation such as show, update, hide, or state
        :param values: (dict) operation arguments, including a panel identifier when needed
        :return:       (dict) decoded service response
        """
        with self._lock:
            if self._socket is None:
                raise DisplayError('The display connection is closed')
            message = dict(values, action=action, token=self._token)
            data = (json.dumps(message) + '\n').encode('utf-8')
            if len(data) > _constants.MAX_MESSAGE_BYTES:
                raise DisplayError('The display command exceeds the message-size limit')
            try:
                self._socket.sendall(data)
                reply = self._reader.readline(_constants.MAX_MESSAGE_BYTES + 1)
                if not reply.endswith(b'\n') or len(reply) > _constants.MAX_MESSAGE_BYTES:
                    raise DisplayError('The display service returned an invalid response')
                response = json.loads(reply)
            except (OSError, ValueError, DisplayError) as err:
                self._disconnect()
                raise DisplayError('Display communication failed: {}'.format(err)) from err
            if not response.get('ok'):
                raise DisplayError(response.get('error', 'The display command failed'))
            return response

    def show(self, kind, **options):
        """
        Show or replace one panel and return a handle scoped to that exact presentation

        :param kind:    (str) registered panel type
        :param options: (dict) display-constructor arguments containing JSON-compatible values
        :return:        (PanelHandle) handle for updating or hiding this presentation
        """
        self.connect()
        identifier = uuid.uuid4().hex
        response = self.request('show', kind=kind, identifier=identifier, options=options)
        return PanelHandle(self, identifier, response.get('accepted', True))

    def _disconnect(self):
        """
        Release the local connection so the service can remove this client's panels
        """
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def close(self):
        """
        Release client-owned panels and stop the service only when this client started it
        """
        with self._lock:
            owned = self._owns_service
            if owned and self._socket is not None:
                try:
                    self.request('shutdown')
                except DisplayError:
                    pass
            self._disconnect()
            if self._process is not None:
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._process.terminate()
                    self._process.wait(timeout=2)
                self._process = None
            self._owns_service = False
            self._start_token = None


class PanelHandle(object):
    """
    Control one presentation without terminating the shared service or a newer replacement
    """

    def __init__(self, client, identifier, accepted=True):
        """
        Retain the owner connection and the service's acceptance of this presentation

        :param client:     (DisplayClient) connection that owns the panel
        :param identifier: (str) unique identifier for this presentation
        :param accepted:   (bool) whether a duplicate-prevention policy allowed the panel
        """
        self._client = client
        self._identifier = identifier
        self._accepted = accepted
        self._closed = not accepted

    @property
    def accepted(self):
        return self._accepted

    @property
    def service_pid(self):
        return self._client.pid

    def is_active(self):
        """
        Report whether this exact presentation still belongs to the connected client
        """
        if self._closed:
            return False
        try:
            active = self._client.request('state', identifier=self._identifier)['active']
        except DisplayError:
            active = False
        self._closed = not active
        return active

    def update(self, **values):
        """
        Apply digit-count or error-state changes to this presentation

        :param values: (dict) JSON-compatible state fields understood by the panel
        """
        self._client.request('update', identifier=self._identifier, values=values)

    def hide(self):
        """
        Retire this presentation while leaving other panels and the shared service running
        """
        if not self._closed:
            try:
                self._client.request('hide', identifier=self._identifier)
            except DisplayError:
                pass
        self._closed = True

    def wait(self, timeout=None):
        """
        Wait for presentation completion only when a caller explicitly requests a blocking wait

        :param timeout: (float) maximum wait in seconds, or None to wait until completion
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_active():
            if deadline is not None and time.monotonic() >= deadline:
                return
            time.sleep(_constants.RETRY_INTERVAL)


_client = None
_client_pid = None


def get_client():
    """
    Return the current process's display connection, avoiding inherited connections after a fork
    """
    global _client, _client_pid
    if _client is None or _client_pid != os.getpid():
        _client = DisplayClient()
        _client_pid = os.getpid()
    return _client
