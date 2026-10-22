#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Read optional overlay metadata without blocking playback or channel commands.
"""
import queue
import threading


class MetadataWorker(object):
    """
    Read optional media metadata off the playback loop and keep only the newest queued request
    """
    def __init__(self, loader, logger):
        """
        Start one bounded worker for optional metadata reads
        """
        self._loader = loader
        self._logger = logger
        self._serial = 0
        self._pending = queue.Queue(maxsize=1)
        self._results = queue.Queue(maxsize=1)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name='fs42-metadata', daemon=True)
        self._thread.start()

    def submit(self, path):
        """
        Replace queued obsolete work with the latest file

        :param path: (str) media path whose optional metadata should be loaded
        :return:     (int) request token for rejecting stale results
        """
        self._serial += 1
        self._replace(self._pending, (self._serial, path))
        return self._serial

    def poll(self):
        """
        Return one completed metadata read without waiting
        """
        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        """
        Stop queued work without waiting for a slow filesystem read
        """
        self._stopped.set()
        self._replace(self._pending, None)

    def _replace(self, target, item):
        """
        Keep only the newest queued request or result
        """
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(item)

    def _run(self):
        """
        Read metadata outside the input loop and publish bounded results
        """
        while not self._stopped.is_set():
            job = self._pending.get()
            if job is None:
                return
            token, path = job
            try:
                data = self._loader(path)
            except Exception as exc:
                self._logger.debug('Optional metadata read failed: {}'.format(exc))
                data = None
            self._replace(self._results, (token, data))
