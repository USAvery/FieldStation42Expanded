#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Observe runtime status-file changes and cache JSON documents without waking an idle display
"""
import os
import json

from PySide6.QtCore import QTimer
from PySide6.QtCore import Signal
from PySide6.QtCore import QObject
from PySide6.QtCore import QFileSystemWatcher


class StatusWatcher(QObject):
    """
    Cache status documents and notify the OSD when watched files change without periodic polling
    """

    changed = Signal(object)

    def __init__(self, paths, parent=None):
        """
        Watch status files and their nearest existing directories so replacements remain observable

        :param paths:  (list) status-file paths, including files that may not exist yet
        :param parent: (QObject) Qt owner responsible for cleanup
        """
        super(StatusWatcher, self).__init__(parent)
        self._paths = {os.path.abspath(path) for path in paths if path}
        self._values = {}
        self._versions = {}
        self._retries = 0
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._queue_refresh)
        self._watcher.directoryChanged.connect(self._queue_refresh)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._refresh)
        self._refresh()

    def read(self, path):
        """
        Return a cached status object without reopening or decoding its file

        :param path: (str) configured status-file path
        :return:     (dict) latest valid document, or None when unavailable
        """
        return self._values.get(os.path.abspath(path)) if path else None

    def _queue_refresh(self, path):
        """
        Coalesce file notifications and allow short retries for a document being rewritten
        """
        self._retries = 2
        self._timer.start(0)

    def _watch_paths(self):
        """
        Restore watches after file replacement and observe directories for files not yet created
        """
        watched = set(self._watcher.files() + self._watcher.directories())
        for path in self._paths:
            directory = os.path.dirname(path)
            while not os.path.isdir(directory):
                directory = os.path.dirname(directory)
            for candidate in (directory, path):
                if candidate not in watched and os.path.exists(candidate):
                    self._watcher.addPath(candidate)
                    watched.add(candidate)

    def _refresh(self):
        """
        Read changed documents once, briefly retry incomplete writes, and rearm filesystem watches
        """
        changed = set()
        retry = False
        self._watch_paths()
        for path in self._paths:
            try:
                info = os.stat(path)
                version = (info.st_mtime_ns, info.st_size, info.st_ino)
                if version == self._versions.get(path):
                    continue
                with open(path, 'r') as f_in:
                    content = f_in.read()
                value = json.loads(content) if content.strip() else None
                self._values[path] = value if isinstance(value, dict) else None
                self._versions[path] = version
                changed.add(path)
            except OSError:
                self._values[path] = None
                self._versions.pop(path, None)
            except ValueError:
                self._values[path] = None
                retry = True
        if changed:
            self.changed.emit(changed)
        if retry and self._retries:
            self._retries -= 1
            self._timer.start(20)
