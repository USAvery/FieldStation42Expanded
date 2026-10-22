#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Coordinate station playback, channel changes, and server shutdown
"""
import json
import time
import shelve
import signal
import logging
import datetime
import multiprocessing
from queue import Empty

from fs42.core.timings import DAYS
from fs42.core.timings import MIN_1
from fs42.tools.field_player import _utils
from fs42.tools.field_player import _constants
from fs42.core.station_manager import StationManager
from fs42.tools.schedule.liquid_manager import LiquidManager
from fs42.tools.field_player.reception import ReceptionStatus
from fs42.tools.field_player.station_player import PlayerState
from fs42.tools.field_player.reception import long_change_effect
from fs42.tools.field_player.reception import none_change_effect
from fs42.tools.field_player.station_player import PlayerOutcome
from fs42.tools.field_player.station_player import StationPlayer
from fs42.tools.field_player.reception import short_change_effect
from fs42.tools.field_player.command_executor import execute_command
from fs42.tools.schedule.live_schedule_agent import LiveScheduleAgent
from fs42.tools.field_player.station_player import update_status_socket


class FieldPlayer(object):
    """
    Own playback state and coordinate the player and API processes
    """

    def __init__(self, transition=None, no_server=False):
        """
        Initialize playback and its child server process
        :param transition: (str)  the channel transition effect
        :param no_server:  (bool) whether to leave the API server stopped
        """
        self._transition = transition
        self._no_server = no_server
        self._transition_fn = short_change_effect
        self._shutdown_queue = None
        self._command_queue = None
        self._api_proc = None
        self._display_client = None
        self._schedule_lock = None
        self._manager = None
        self._reception = None
        self._logger = None
        self._schedule_agent = None
        self._channel_socket = None
        self._channel_index = None
        self._player = None
        self._channel_conf = None
        self._player_state = None
        self._skip_play = None
        self._stuck_timer = None
        self._check_args()

    def _check_args(self):
        """
        Check the selected transition effect
        """
        effects = {'long': long_change_effect, 'short': short_change_effect, 'none': none_change_effect}
        if self._transition is None:
            return
        if self._transition not in effects:
            msg = 'Unknown channel transition: {}'.format(self._transition)
            raise _utils.FieldPlayerError(msg)
        self._transition_fn = effects[self._transition]

    def _start_server(self):
        """
        Start the API process with a command and shutdown queue
        """
        self._schedule_lock = multiprocessing.Lock()
        if self._no_server:
            return
        self._shutdown_queue = multiprocessing.Queue()
        self._command_queue = multiprocessing.Queue()
        self._api_proc = multiprocessing.Process(target=_utils.start_api_server,
                                                 args=(self._shutdown_queue, self._command_queue), daemon=True)
        self._api_proc.start()

    def _stop_server(self):
        """
        Ask the API process to stop and wait for it to finish
        """
        if self._shutdown_queue is not None:
            self._shutdown_queue.put('shutdown')
        if self._api_proc is not None:
            self._api_proc.join(timeout=5)

    def _start_display(self):
        """
        Connect to the shared display service or start it without loading Qt into this process
        """
        from fs42.tools.display.client import get_client
        try:
            self._display_client = get_client()
            self._display_client.connect()
        except Exception as err:
            logging.getLogger('field_player').warning('Display service unavailable: {}'.format(err))

    def _stop_display(self):
        """
        Release player-owned panels and stop the service when this player started it
        """
        if self._display_client is not None:
            self._display_client.close()
            self._display_client = None

    def _run_ticker(self, message, header, style, iterations):
        """
        Start the optional ticker overlay
        """
        from fs42.tools.overlay import run_ticker
        run_ticker(message, header, style, iterations)

    def run(self):
        """
        Start the server and play stations until shutdown
        """
        # Start the API process
        self._start_server()
        try:
            self._start_display()
            # Run the station playback loop
            self._play_stations()
        finally:
            # Release the display service and child server process
            self._stop_display()
            self._stop_server()

    def _check_input(self):
        """
        Consume queued or file-based player commands and translate them into playback outcomes

        Apply commands handled directly by the controller, such as schedule reloads and
        tickers, and return state transitions for the active playback loop.

        :return: (PlayerOutcome) pending playback command, or None when no transition is requested
        """
        if self._command_queue:
            q_message = None
            try:
                q_message = self._command_queue.get(block=False)
            except Empty:
                pass

            if q_message:
                command = q_message.get('command', None)
                if not command:
                    return
                match command:
                    case 'exit':
                        return PlayerOutcome(PlayerState.EXIT_COMMAND)
                    case 'reload_data':
                        LiquidManager().reload_schedules()
                    case 'guide':
                        if StationManager().guide_config:
                            # The guide is an overlay, not a channel change. Keeping this
                            # non-interrupting lets the currently tuned station continue
                            # playing underneath the guide preview.
                            return PlayerOutcome(PlayerState.SUCCESS, 'guide_toggle')
                        logging.getLogger('InputCheck').warning('Guide channel not configured')
                    case 'ticker':
                        message = q_message.get('message', None)
                        header = q_message.get('header', None)
                        style = q_message.get('style', None)
                        iterations = q_message.get('iterations', None)
                        self._run_ticker(message, header, style, iterations)
                    case 'play_file':
                        file_path = q_message.get('file_path', None)
                        return PlayerOutcome(PlayerState.PLAY_FILE, file_path)
                    case 'web_key':
                        key = q_message.get('key', '')
                        return PlayerOutcome(PlayerState.SUCCESS, 'web_key:{}'.format(key))
                    case 'mpv_command':
                        action = q_message.get('action', '')
                        return PlayerOutcome(PlayerState.SUCCESS, 'mpv_command:{}'.format(action))
                    case 'parental_digit':
                        digit = str(q_message.get('digit', ''))
                        return PlayerOutcome(PlayerState.SUCCESS, 'parental_digit:{}'.format(digit))
                    case 'parental_clear':
                        return PlayerOutcome(PlayerState.SUCCESS, 'parental_clear')
        channel_socket = StationManager().server_conf['channel_socket']
        with open(channel_socket, 'r') as r_sock:
            contents = r_sock.read()
        if len(contents):
            with open(channel_socket, 'w'):
                pass
            return PlayerOutcome(PlayerState.CHANNEL_CHANGE, contents)
        return None

    def _setup_playback(self):
        """
        Load the initial station and prepare playback
        """
        self._manager = StationManager()
        self._reception = ReceptionStatus()
        self._logger = logging.getLogger('MainLoop')
        self._logger.info('Starting main loop')
        self._schedule_agent = None
        agent_conf = self._manager.server_conf.get('schedule_agent')
        if agent_conf and self._schedule_lock:
            self._schedule_agent = LiveScheduleAgent(agent_conf, self._schedule_lock)
            self._logger.info('Live schedule agent is active')
        else:
            self._logger.info('Live schedule agent is not configured')
        self._channel_socket = StationManager().server_conf['channel_socket']
        with open(self._channel_socket, 'w'):
            pass
        if not len(self._manager.stations):
            self._logger.error('Could not find any station runtimes - do you have your channels configured?')
            self._logger.error('Check to make sure you have valid json configurations in the confs dir')
            self._logger.error(
                'The confs/examples folder contains working examples that you can build off of - just move one into confs/'
            )
            return
        self._channel_index = 0
        start_channel_config = StationManager().server_conf.get('start_channel', None)
        if not start_channel_config:
            use_saved = StationManager().server_conf.get('recall_last_channel', True)
            if use_saved:
                with shelve.open(_constants.STATE_SHELVE) as s:
                    self._channel_index = s.get('channel_index', 0)
        else:
            self._channel_index = self._manager.index_from_channel(start_channel_config)
            if not self._channel_index:
                self._logger.error(
                    "Start channel specified as {} in main_config.json, but station doesn't exist.".format(
                        start_channel_config))
                self._logger.warning('Attempting fallback to the first channel')
                self._channel_index = 0
        if self._channel_index >= len(self._manager.stations):
            self._logger.warning('Saved channel index %d is out of range, resetting to 0', self._channel_index)
            self._channel_index = 0
        self._player = StationPlayer(self._manager.stations[self._channel_index], self._check_input)
        if self._schedule_lock:
            self._player.schedule_lock = self._schedule_lock
        stand_by = StationManager().server_conf.get('standby_image', 'runtime/standby.png')
        self._reception.degrade()
        self._player.update_filters()
        self._player.play_file(stand_by)
        self._player.load_up()
        self._player.preload_guide_overlay()
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
        self._channel_conf = self._manager.stations[self._channel_index]
        self._player_state = None
        self._skip_play = False
        self._stuck_timer = 0

    def _shutdown(self, sig=None, frame=None):
        """
        Stop playback and the API process
        """
        self._logger.critical('Received sig-int signal, attempting to exit gracefully...')
        self._player._shutdown_guide_overlay()
        self._player.shutdown()
        update_status_socket('stopped', '', -1)
        if self._shutdown_queue is not None:
            self._shutdown_queue.put('shutdown')
        if self._api_proc is not None:
            self._api_proc.join(timeout=5)
        self._logger.info('Shutdown completed as expected - exiting application')
        exit(0)

    def _play_current_station(self):
        """
        Play the current station at its scheduled position
        """
        if self._channel_conf['network_type'] == 'guide' and not self._skip_play:
            self._logger.info('Starting the guide channel')
            self._player_state = self._player.show_guide(self._channel_conf)
        elif self._channel_conf['network_type'] == 'web' and not self._skip_play:
            self._logger.info('Starting the web channel')
            self._player_state = self._player.show_web(self._channel_conf)
        elif self._channel_conf['network_type'] == 'executable' and not self._skip_play:
            self._logger.info('Starting an executable channel')
            self._player.stop_player()
            self._player_state = execute_command(self._channel_conf, self._check_input)
        elif not self._skip_play:
            now = datetime.datetime.now()

            week_day = DAYS[now.weekday()]
            hour = now.hour
            skip = now.minute * MIN_1 + now.second

            self._logger.info('Starting station {0} at: {1} {2} skipping={3} '.format(
                self._channel_conf['network_name'], week_day, hour, skip))

            self._player_state = self._player.play_slot(self._channel_conf['network_name'],
                                                        datetime.datetime.now())

    def _change_channel(self):
        """
        Resolve a channel change and save the new selection
        """
        self._stuck_timer = 0
        self._player._close_guide_overlay()
        self._player.parental_unlocked_network = None
        self._player._close_now_playing()
        station_cache = self._manager.stations
        stations_len = len(station_cache)
        tune_up = True
        if self._player_state.payload:
            try:
                as_obj = json.loads(self._player_state.payload)
                if 'command' in as_obj:
                    if as_obj['command'] == 'direct':
                        tune_up = False
                        if 'channel' in as_obj:
                            self._logger.debug('Got direct tune command for channel {}'.format(as_obj['channel']))
                            new_index = self._manager.index_from_channel(as_obj['channel'])
                            if new_index is None:
                                self._logger.warning(
                                    'Got direct tune command but could not find station with channel {}'.format(
                                        as_obj['channel']))
                            else:
                                self._channel_index = new_index

                        else:
                            self._logger.critical('Got direct tune command, but no channel specified')
                    elif as_obj['command'] == 'up':
                        tune_up = True
                        self._logger.debug('Got channel up command')
                    elif as_obj['command'] == 'down':
                        tune_up = False
                        self._logger.debug('Got channel down command')
                        found = False
                        while not found:
                            self._channel_index -= 1

                            if self._channel_index < 0:
                                self._channel_index = stations_len - 1
                            if not station_cache[self._channel_index]['hidden']:
                                found = True

            except Exception as e:
                self._logger.exception(e)
                self._logger.warning('Got payload on channel change, but JSON convert failed')
        if tune_up:
            self._logger.info('Starting channel change')
            found = False
            while not found:
                self._channel_index += 1
                self._channel_index = self._channel_index if self._channel_index < stations_len else 0
                found = not station_cache[self._channel_index]['hidden']
        with shelve.open(_constants.STATE_SHELVE) as s:
            s['channel_index'] = self._channel_index
        self._channel_conf = station_cache[self._channel_index]
        self._player.station_config = self._channel_conf
        self._transition_fn(self._player, self._reception)

    def _handle_failed_playback(self):
        """
        Show standby content and check for a recovery command
        """
        self._stuck_timer += 1
        if self._stuck_timer == 2:
            stand_by = self._channel_conf.get(
                'standby_image',
                StationManager().server_conf.get('standby_image', 'runtime/standby.png'))
            self._player.play_file(stand_by)
        current_title_on_stuck = self._player.get_current_path()
        update_status_socket(
            'stuck',
            self._channel_conf['network_name'],
            self._channel_conf['channel_number'],
            current_title_on_stuck,
        )
        time.sleep(1)
        self._logger.critical('Player failed to start - resting for 1 second and trying again')
        new_state = self._check_input()
        if new_state is not None:
            self._player_state = new_state
            # set skip play so outcome isn't overwritten
            # and the channel change can be processed next loop
            self._skip_play = True

    def _handle_outcome(self):
        """
        Handle the latest playback outcome
        """
        if self._player_state.status == PlayerState.CHANNEL_CHANGE:
            self._change_channel()
        elif self._player_state.status == PlayerState.PARENTAL_CONTROLS:
            self._stuck_timer = 0
            self._player_state = self._player.prompt_parental_controls(self._channel_conf)
            if self._player_state.status != PlayerState.SUCCESS:
                self._skip_play = True
        elif self._player_state.status == PlayerState.PLAY_FILE:
            self._logger.info('Play file: {}'.format(self._player_state.payload))
            self._skip_play = True
            self._player_state = self._player.play_and_wait(self._player_state.payload)
        elif self._player_state.status == PlayerState.FAILED:
            self._handle_failed_playback()
        elif self._player_state.status == PlayerState.SUCCESS:
            self._stuck_timer = 0
        elif self._player_state.status == PlayerState.EXIT_COMMAND:
            self._shutdown(None, None)
        else:
            self._stuck_timer = 0

    def _play_stations(self):
        """
        Play stations and process commands until shutdown
        """
        # Prepare the station and optional live scheduler
        self._setup_playback()
        if self._player is None:
            return
        while True:
            # Keep the live schedule current
            if self._schedule_agent:
                self._schedule_agent.tick()

            # Play the selected station and process its result
            self._logger.info('Playing station: {}'.format(self._channel_conf['network_name']))
            self._play_current_station()
            self._logger.debug('Got player outcome: {}'.format(self._player_state.status))
            self._skip_play = False
            self._handle_outcome()
