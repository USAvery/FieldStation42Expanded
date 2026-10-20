#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage live schedule agent
"""
import logging
import datetime
import multiprocessing


def _worker_build_schedules(lock, stations_to_build, amount_to_add):
    """
    Worker build schedules
    """
    _l = logging.getLogger('ScheduleAgent.Worker')
    _l.info('Worker started - building {0} for {1} station(s)'.format(amount_to_add, len(stations_to_build)))

    # import here to avoid issues with multiprocessing and module state
    from fs42.tools.schedule.liquid_schedule import LiquidSchedule

    for station_conf in stations_to_build:
        name = station_conf['network_name']
        try:
            _l.info('Building {0} of schedule for {1}'.format(amount_to_add, name))
            with lock:
                schedule = LiquidSchedule(station_conf)
                schedule.add_amount(amount_to_add)
            _l.info('Finished building schedule for {}'.format(name))
        except Exception as e:
            _l.error('Failed to build schedule for {0}: {1}'.format(name, e))

    _l.info('Worker finished')


class LiveScheduleAgent(object):
    """
    LiveScheduleAgent
    """
    # map config strings to timedeltas for the trigger threshold
    _trigger_deltas = {
        'day': datetime.timedelta(days=1),
        'week': datetime.timedelta(weeks=1),
        'month': datetime.timedelta(days=30),
    }

    def __init__(self, schedule_agent_conf, lock):
        """
        Initialize the instance
        """
        self._l = logging.getLogger('ScheduleAgent')
        self._lock = lock
        self._amount_to_add = schedule_agent_conf['amount_to_add']
        self._trigger_at = schedule_agent_conf['trigger_add_at']
        self._trigger_delta = self._trigger_deltas[self._trigger_at]
        self._worker = None
        self._last_check = None
        self._check_interval = datetime.timedelta(hours=1)
        self._l.info('Live schedule agent initialized: trigger_at={0}, amount_to_add={1}'.format(
            self._trigger_at, self._amount_to_add))

    def get_lock(self):
        """
        Get lock
        """
        return self._lock

    def _needs_check(self):
        """
        Needs check
        """
        now = datetime.datetime.now()
        if self._last_check is None:
            self._last_check = now
            return True
        if now - self._last_check >= self._check_interval:
            self._last_check = now
            return True
        return False

    def _find_stations_needing_schedules(self):
        """
        Find stations needing schedules
        """
        from fs42.tools.schedule.liquid_manager import LiquidManager
        from fs42.core.station_manager import StationManager

        liquid = LiquidManager()
        now = datetime.datetime.now()
        threshold = now + self._trigger_delta
        needs_build = []

        for station in StationManager().stations:
            if not station.get('_has_schedule', False):
                continue
            name = station['network_name']
            try:
                (start, end) = liquid.get_extents(name)
                if end is None or end < threshold:
                    self._l.info('{0} schedule ends at {1}, threshold is {2} - needs build'.format(
                        name, end, threshold))
                    needs_build.append(station)
            except ValueError:
                continue

        return needs_build

    def _worker_finished(self):
        """
        Worker finished
        """
        if self._worker is None:
            return False
        if self._worker.is_alive():
            return False

        exitcode = self._worker.exitcode
        if exitcode != 0:
            self._l.warning('Schedule build worker exited with code {}'.format(exitcode))
        else:
            self._l.info('Schedule build worker completed successfully')

        self._worker = None
        return True

    def tick(self):
        """
        Tick
        """
        # first, check if a previous worker finished
        if self._worker_finished():
            from fs42.tools.schedule.liquid_manager import LiquidManager

            self._l.info('Reloading schedules after background build')
            LiquidManager().reload_schedules()
            return True

        # don't spawn a new worker if one is running
        if self._worker is not None:
            return False

        # only check periodically
        if not self._needs_check():
            return False

        stations = self._find_stations_needing_schedules()
        if not stations:
            return False

        self._l.info('Spawning worker to build schedules for {} station(s)'.format(len(stations)))
        self._worker = multiprocessing.Process(
            target=_worker_build_schedules,
            args=(self._lock, stations, self._amount_to_add),
            daemon=True,
        )
        self._worker.start()
        return False
