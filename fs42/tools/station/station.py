#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Coordinate catalog, sequence, and schedule administration
"""
import logging
import sqlite3
import datetime

from rich.panel import Panel
from rich.console import Console

from fs42.core import logger
from fs42.tools.station import _utils
from fs42.tools.station import _constants
from fs42.tools.sequence import sequence_api
from fs42.tools.catalog.catalog import ShowCatalog
from fs42.core.station_manager import StationManager
from fs42.tools.media.fluid_builder import FluidBuilder
from fs42.tools.schedule.liquid_manager import LiquidManager
from fs42.tools.schedule.liquid_schedule import LiquidSchedule

_logger = logger.setup('fs42.tools.station')


class Station(object):
    """
    Run the requested station administration operations
    """

    def __init__(self, args, start_server=False):
        """
        Initialize station administration

        :param args:         (obj)  the parsed command-line options
        :param start_server: (bool) whether a bare invocation starts the console
        """
        self._args = args
        self._start_server = start_server
        self._success_messages = []
        self._failure_messages = []
        self._console = Console(color_system='standard', force_terminal=True)
        self._start_time = datetime.datetime.now()
        self._check_args()

    @property
    def success_messages(self):
        return list(self._success_messages)

    @property
    def failure_messages(self):
        return list(self._failure_messages)

    def _check_args(self):
        """
        Check that station options were supplied
        """
        if self._args is None:
            msg = 'Must provide station options'
            raise _utils.StationError(msg)

    def _get_stations(self, names):
        """
        Resolve station names, using all stations for an empty selection
        """
        manager = StationManager()
        if not names:
            return manager.stations
        stations = []
        for name in names:
            station = manager.station_by_name(name)
            if station is None:
                msg = "Can't find station by name: {}".format(name)
                raise _utils.StationError(msg)
            stations.append(station)
        return stations

    def _report_failure(self, action, err):
        """
        Record a failed operation and its traceback
        """
        msg = 'Failed to {}: {}'.format(action, err)
        _logger.exception(msg)
        self._failure_messages.append(msg)

    def _run_for_stations(self, names, capability, action, function):
        """
        Apply an operation to each eligible station and collect its result
        """
        try:
            stations = self._get_stations(names)
        except Exception as err:
            self._report_failure('find stations to {}'.format(action), err)
            return
        for station in stations:
            if not station[capability]:
                continue
            description = '{} for {}'.format(action, station['network_name'])
            _logger.info(description)
            try:
                function(station)
                self._success_messages.append('Completed {}'.format(description))
            except Exception as err:
                self._report_failure(description, err)

    def _configure_logging(self):
        """
        Apply verbosity and optional file logging
        """
        if self._args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        if self._args.logfile:
            handler = logging.FileHandler(self._args.logfile)
            handler.setFormatter(logging.Formatter(_constants.LOG_FORMAT))
            logging.getLogger().addHandler(handler)

    def _limit_memory(self):
        """
        Apply the requested Linux address-space limit
        """
        if not self._args.limit_memory:
            return
        import resource
        percent = min(1.0, max(0.1, self._args.limit_memory[0]))
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        limit = int(_utils.get_available_memory() * 1024 * percent)
        resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
        _logger.info('Reducing available memory usage')

    def _clear_cache(self, name):
        """
        Clear cached scan results
        """
        table = _constants.CACHE_TABLES[name]
        with sqlite3.connect(FluidBuilder().db_path) as connection:
            connection.execute('DELETE FROM {}'.format(table))
        self._success_messages.append('Cleared cached {}'.format(name))

    def _print_catalog(self):
        """
        Display the requested catalog
        """
        try:
            station = self._get_stations([self._args.printcat])[0]
            self._console.print(ShowCatalog(station).get_text_listing())
            self._success_messages.append('Printed catalog for {}'.format(self._args.printcat))
        except Exception as err:
            self._report_failure('print catalog', err)

    def _run_report(self):
        """
        Run an exclusive report or cache reset and return whether one was selected
        """
        if self._args.reset_chapters:
            self._clear_cache('chapters')
        elif self._args.reset_breaks:
            self._clear_cache('breaks')
        elif self._args.schedule:
            self._console.print(LiquidManager().get_summary())
        elif self._args.printcat is not None:
            self._print_catalog()
        elif self._args.print_schedule:
            try:
                LiquidManager().print_schedule(self._args.print_schedule, self._args.verbose)
            except Exception as err:
                self._report_failure('print schedule', err)
        elif self._args.check_catalogs is not None:
            self._run_for_stations(self._args.check_catalogs, '_has_catalog', 'check catalog', self._check_catalog)
        else:
            return False
        self._report_outcome()
        return True

    def _check_catalog(self, station):
        """
        Check a station's existing catalog
        """
        ShowCatalog(station).check_catalog()

    def _rebuild_catalog(self, station):
        """
        Rebuild a station's catalog with the selected scan options
        """
        ShowCatalog(station, rebuild_catalog=True, force=self._args.force,
                    skip_chapter_scan=self._args.skip_chapter_scan)

    def _update_catalogs(self):
        """
        Reset schedules and rebuild selected catalogs
        """
        if self._args.delete_schedules is not None:
            self._run_for_stations(self._args.delete_schedules, '_has_schedule', 'reset schedule',
                                   LiquidManager().reset_schedule)
        if self._args.rebuild_catalog is None:
            return
        self._run_for_stations(self._args.rebuild_catalog, '_has_schedule', 'reset schedule',
                               LiquidManager().reset_schedule)
        self._run_for_stations(self._args.rebuild_catalog, '_has_catalog', 'rebuild catalog',
                               self._rebuild_catalog)
        if _constants.USE_FLUID_FILE_CACHE:
            try:
                FluidBuilder().trim_file_cache(self._start_time)
            except Exception as err:
                self._report_failure('trim the fluid cache', err)

    def _update_sequences(self):
        """
        Scan or rebuild selected station sequences
        """
        if self._args.scan_sequences is not None:
            self._run_for_stations(self._args.scan_sequences, '_has_catalog', 'scan sequences',
                                   sequence_api.scan_sequences)
        if self._args.rebuild_sequences is not None:
            self._run_for_stations(self._args.rebuild_sequences, '_has_catalog', 'rebuild sequences',
                                   sequence_api.rebuild_sequences)

    def _scan_media(self):
        """
        Scan selected directories for breaks and chapter markers
        """
        if self._args.break_detect_dir is not None:
            FluidBuilder().scan_breaks(self._args.break_detect_dir)
        if self._args.chapter_detect_dir is not None:
            FluidBuilder().scan_chapters(self._args.chapter_detect_dir)

    def _add_day(self, station):
        """
        Add one day to a station schedule
        """
        LiquidSchedule(station).add_days(1)

    def _add_week(self, station):
        """
        Add one week to a station schedule
        """
        LiquidSchedule(station).add_week()

    def _add_month(self, station):
        """
        Add one month to a station schedule
        """
        LiquidSchedule(station).add_month()

    def _extend_schedules(self):
        """
        Extend selected station schedules
        """
        operations = [(self._args.add_day, 'add a day', self._add_day),
                      (self._args.add_week, 'add a week', self._add_week),
                      (self._args.add_month, 'add a month', self._add_month)]
        for names, action, function in operations:
            if names is None:
                continue
            self._run_for_stations(names, '_has_schedule', action, function)

    def _report_outcome(self):
        """
        Display successes and failures
        """
        self._console.print('[bold blue underline]Finished running FieldStation42.[/bold blue underline]')
        for msg in self._success_messages:
            self._console.print('[green]{}[/green]'.format(msg))
        for msg in self._failure_messages:
            self._console.print('[red]{}[/red]'.format(msg))

    def _run_server(self):
        """
        Start the web console when requested
        """
        if not self._args.server and not self._start_server:
            return
        from fs42.web.app import mount_fs42_api
        self._console.print(
            Panel.fit(_constants.SERVER_MESSAGE, title='FieldStation42', subtitle="It's Up To You.",
                      border_style='blue'))
        mount_fs42_api()

    def run(self):
        """
        Run the selected station operations
        """
        if self._args.graphical_interface:
            from fs42.tools.station.gui.ux import StationApp
            return StationApp().run()

        # Configure diagnostics and resource limits
        self._configure_logging()
        self._limit_memory()
        if self._run_report():
            return

        # Update catalogs, sequences, and schedules
        self._update_catalogs()
        self._update_sequences()
        self._scan_media()
        self._extend_schedules()

        # Report results and start the console
        self._report_outcome()
        self._run_server()
