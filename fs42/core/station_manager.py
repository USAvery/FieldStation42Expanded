#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Load station configuration and share the active station registry
"""
import os
import copy
import logging

from fs42.core import _constants
from fs42.core.station_io import StationIO
from fs42.tools.schedule import slot_reader
from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.core.station_manager')


class StationConfigError(Exception):
    pass


def _schedule_error_message(e):
    """
    Turn a missing schedule key into a readable error, retaining other exception text
    """

    if isinstance(e, KeyError):
        return 'No schedule defined for {}'.format(e.args[0]) if e.args else 'Incomplete schedule'
    return str(e)


class StationManager(object):
    """
    Share global settings and the active station registry across manager instances
    """
    # the borg singleton pattern
    __we_are_all_one = {}
    _initialized = False

    __main_config_path = 'confs/main_config.json'

    # public visible - be careful
    stations = []
    no_catalog = {'guide', 'streaming', 'web', 'executable'}
    no_schedule = {'guide', 'streaming', 'web', 'executable'}

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        """
        Create a manager whose attributes share the common station registry state
        """
        obj = super(StationManager, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj

    def __init__(self):
        """
        Load global settings and active stations once, then validate the guide configuration
        """
        self.__dict__ = self.__we_are_all_one
        if not self._initialized:
            self._initialized = True
            if not len(self.stations):
                self.station_io = StationIO()
                self.server_conf = copy.deepcopy(_constants.DEFAULT_SERVER_CONF)
                self._number_index = {}
                self._name_index = {}
                self.skipped_stations = []
                self.load_main_config()
                self.load_json_stations()
            self.guide_config = None
            for i in range(len(self.stations)):
                station = self.stations[i]
                if station['network_type'] == 'guide':
                    self.guide_config = station
                    logging.getLogger().info('Loading and checking guide channel')
                    from fs42.tools.guide.guide_tk import GuideWindowConf

                    gconf = GuideWindowConf()
                    errors = gconf.check_config(station)
                    if len(errors):
                        logging.getLogger().error('Errors found in Guide Channel configuration:')
                        for err in errors:
                            logging.getLogger().error(err)
                        logging.getLogger().error('Please check your configuration and try agian.')
                        raise StationConfigError('Errors found in Guide Channel configuration: ' +
                                                 '; '.join(str(e) for e in errors))
                    else:
                        logging.getLogger().info('Guide channel checks completed.')
                elif station['network_type'] == 'web':
                    #determine if the URL is to a custom guide
                    if 'static/customguide/customguide.html' in station['web_url']:
                        self.guide_config = station
                        logging.getLogger().info('Setting web channel as guide channel')

    def station_by_name(self, name):
        """
        Look up an active station by its network name, returning None when absent
        """
        if name in self._name_index:
            return self._name_index[name]
        return None

    def station_by_channel(self, channel_number):
        """
        Look up an active station by channel number, returning None when absent
        """
        if channel_number in self._number_index:
            return self._number_index[channel_number]
        return None

    def index_from_channel(self, channel):
        """
        Find a channel's zero-based position in the active station list, or return None
        """
        index = 0
        for station in self.stations:
            if station['channel_number'] == channel:
                return index
            index += 1
        return None

    def get_day_parts(self):
        """
        Return the configured day-part names and their allowed hours
        """
        return self.server_conf['day_parts']

    def get_custom_holidays(self):
        """
        Return the configured custom holiday definitions used by scheduling hints
        """
        return self.server_conf['custom_holidays']

    def _validate_custom_holiday_names(self):
        """
        Reject custom holiday names that would also match a built-in scheduling hint
        """
        # a holiday name is matched against folder names and marathon hints as a
        # bare string, so one that also reads as a built-in hint either stacks with
        # it (folders apply every match) or loses to it (marathons take the first).
        # both fail quietly, so reject the name instead.
        # imported here rather than at module scope - schedule_hint imports
        # station_manager, so a top level import would be circular
        from fs42.tools.schedule import schedule_hint

        others = [
            klass for klass in schedule_hint.FOLDER_HINT_KLASSES if klass is not schedule_hint.CustomHolidayHint
        ] + [schedule_hint.BumpHint]

        for name in self.server_conf.get('custom_holidays', {}):
            conflict = schedule_hint.hint_klass_matcher(name, klasses=others)
            if conflict:
                raise ValueError(
                    "Custom holiday name '{0}' collides with the {1} hint type. Pick a name that isn't a month, quarter, weekday, day part, week number, date range, or bump position."
                    .format(name, conflict.__name__))

    def load_main_config(self):
        """
        Merge global configuration overrides into defaults and validate scheduling settings

        Compile-check title patterns, expand day-part hours, and reject holiday name
        collisions. Wrap configuration-loading failures in StationConfigError.
        """
        _l = logging.getLogger('STATIONMANAGER')
        d = self.station_io.load_main_config()

        if d is not None:
            try:
                to_check = [
                    'channel_socket',
                    'status_socket',
                    'time_format',
                    'start_mpv',
                    'db_path',
                    'server_host',
                    'server_port',
                    'normalize_titles',
                    'tmdb_api_key',
                    'recall_last_channel',
                    'schedule_agent',
                    'video_seek_timeout',
                    'stream_start_timeout',
                    'overlay_conf',
                    'start_channel',
                    'follow_static_symlinks',
                    'parental_controls_pin',
                    'parental_controls_theme',
                    'custom_holidays',
                ]

                for key in to_check:
                    if key in d:
                        self.server_conf[key] = d[key]

                # Load custom title patterns if provided
                if 'title_patterns' in d:
                    import re
                    custom_patterns = []
                    for i, pattern_config in enumerate(d['title_patterns']):
                        try:
                            # Validate that required fields exist
                            if 'pattern' not in pattern_config:
                                _l.error("title_patterns[{}]: missing 'pattern' field".format(i))
                                continue
                            if 'group' not in pattern_config:
                                _l.error("title_patterns[{}]: missing 'group' field".format(i))
                                continue

                            # Validate that the regex compiles
                            re.compile(pattern_config['pattern'])

                            # Add as tuple (pattern, group) to match existing format
                            custom_patterns.append((pattern_config['pattern'], pattern_config['group']))

                            desc = pattern_config.get('description', 'Custom pattern {}'.format(i + 1))
                            _l.info('Loaded custom title pattern: {}'.format(desc))
                        except re.error as e:
                            _l.error('Invalid regex in title_patterns[{0}]: {1}'.format(i, e))
                            _l.error('Pattern was: {}'.format(pattern_config.get('pattern', 'N/A')))

                    self.server_conf['title_patterns'] = custom_patterns
                    if custom_patterns:
                        _l.info('Loaded {} custom title pattern(s)'.format(len(custom_patterns)))

                if 'day_parts' in d:
                    new_parts = {}
                    for key in d['day_parts']:
                        start_hour = d['day_parts'][key]['start_hour']
                        end_hour = d['day_parts'][key]['end_hour']
                        if end_hour > start_hour:
                            new_parts[key] = range(start_hour, end_hour)
                        else:
                            # wraps midnight - manually build the list of hours
                            hours = []
                            hour = start_hour
                            while hour <= 23:
                                hours.append(hour)
                                hour += 1
                            hour = 0
                            while hour <= end_hour:
                                hours.append(hour)
                                hour += 1
                            new_parts[key] = hours
                    self.server_conf['day_parts'] = new_parts

                # has to run after day_parts is final, since a holiday can collide
                # with a custom day part name just as easily as a built-in one
                self._validate_custom_holiday_names()

                if 'date_time_format' not in d:
                    # check the environment variable or set default then
                    self.server_conf['date_time_format'] = os.environ.get('FS42_TS', '%Y-%m-%dT%H:%M:%S')
                else:
                    self.server_conf['date_time_format'] = d['date_time_format']

            except Exception as e:
                _logger.info(e)
                _l.exception(e)
                _l.error('Error loading main config overrides from {}'.format(self.station_io.main_config_path))
                raise StationConfigError('Error loading main config overrides from {0}: {1}'.format(
                    self.station_io.main_config_path, e)) from e
        # else: skip, no overrides (title_patterns already initialized to [] in __init__)

    def load_json_stations(self):
        """
        Reload usable stations, normalize standard schedules, and rebuild channel lookups

        Keep invalid station details in skipped_stations for diagnostics and sort the
        active registry by channel number.
        """
        _l = logging.getLogger('STATIONMANAGER')

        try:
            # Let StationIO do all the heavy lifting
            station_configs, skipped = self.station_io.load_and_process_all_stations()
        except Exception as e:
            _l.error('*' * 60)
            _l.error('Error loading station configurations')
            _l.exception(e)
            _l.error('*' * 60)
            raise StationConfigError('Error loading station configurations: {}'.format(e)) from e

        loaded = []
        for station in station_configs:
            if station['network_type'] == 'standard':
                try:
                    station = slot_reader.smooth_tags(station)
                except Exception as e:
                    network_name = station.get('network_name')
                    _l.error('*' * 60)
                    _l.error('Skipping station with unusable schedule: {}'.format(network_name))
                    _l.error('Station will not be live until this is fixed: {}'.format(e))
                    _l.error('*' * 60)
                    skipped.append({
                        'filename': self.station_io.find_config_by_network_name(network_name),
                        'network_name': network_name,
                        'error': _schedule_error_message(e),
                    })
                    continue
            loaded.append(station)

        self.stations = sorted(loaded, key=lambda station: station['channel_number'])
        self.skipped_stations = skipped
        self._build_indexes()

        if skipped:
            _l.warning('{} station config(s) skipped and not live:'.format(len(skipped)))
            for entry in skipped:
                _l.warning('  {0}: {1}'.format(entry['filename'], entry['error']))

    def _build_indexes(self):
        """
        Build name and channel number indexes for fast lookup
        """
        _l = logging.getLogger('STATIONMANAGER')
        self._name_index = {}
        self._number_index = {}
        for station in self.stations:
            name = station['network_name']
            number = station['channel_number']
            if name in self._name_index:
                _l.warning("Duplicate network_name '{}' - only one will be reachable by name".format(name))
            if number in self._number_index:
                _l.warning('Duplicate channel_number {} - only one will be reachable by channel'.format(number))
            self._name_index[name] = station
            self._number_index[number] = station

    def write_station_config(self, network_name, config_data, is_update=False):
        """
        Save a station configuration and refresh the active registry after a successful write

        :param network_name: (str) current network name used to locate an existing station
        :param config_data:  (dict) complete station document to validate and save
        :param is_update:    (bool) whether this replaces an existing station
        :return:             (tuple) success flag, status message, and written path or None
        """

        # Let StationIO handle validation, uniqueness checks, and file writing
        success, message, file_path = self.station_io.save_station_config(network_name, config_data, is_update)

        if success:
            # Reload the station configuration
            self._reload_stations()

        return success, message, file_path

    def delete_station_config(self, network_name):
        """
        Delete a saved station and refresh the active registry if deletion succeeds

        :param network_name: (str) stored network name of the station to remove
        :return:             (tuple) success flag and status or error message
        """

        # Let StationIO handle existence checks and file deletion
        success, message = self.station_io.remove_station_config(network_name)

        if success:
            # Reload stations
            self._reload_stations()

        return success, message

    def _reload_stations(self):
        """
        Reload station files and rebuild the shared name and channel indexes
        """

        _l = logging.getLogger('STATIONMANAGER')
        _l.info('Reloading station configurations...')

        # Reload from disk - smooths tags and rebuilds indexes
        self.load_json_stations()

        _l.info('Reloaded {} station(s)'.format(len(self.stations)))
