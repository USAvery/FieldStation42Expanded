#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Hold background-build results, synchronization locks, and CPU-sampling state owned by one web
application instance.
"""
import threading


class WebState(object):
    """
    Keep background task logs, synchronization locks, and CPU samples for one web application
    """

    def __init__(self):
        """
        Initialize state owned by one web application
        """
        self.rebuild_tasks = {}
        self.rebuild_tasks_lock = threading.Lock()
        self.add_time_tasks = {}
        self.add_time_tasks_lock = threading.Lock()
        self.cpu_sample = None
        self.cpu_sample_time = 0.0
        self.cpu_usage_percent = None
