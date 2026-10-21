#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Load station schedules and locate the programming block and playback offset for a requested time.
Provide schedule summaries, resets, and synthetic streaming play points.
"""
import logging
import datetime

from fs42.tools.schedule import liquid_api
from fs42.tools.sequence import sequence_api
from fs42.core import logger as project_logger
from fs42.tools.catalog.catalog import ShowCatalog
from fs42.core.station_manager import StationManager
from fs42.tools.schedule.liquid_blocks import BlockPlanEntry

_logger = project_logger.setup('fs42.tools.schedule.liquid_manager')


class ScheduleQueryNotInBounds(Exception):
    pass


class ScheduleNotFound(Exception):
    pass


class PlayPoint(object):
    """
    Identify the active playback segment and elapsed offset within a scheduled program
    """

    def __init__(self, index, offset, plan, block_title='Unknown'):
        """
        Store the segment position needed to join a program already in progress

        :param index:       (int) zero-based active entry index in the playback plan
        :param offset:      (float) elapsed seconds within that entry
        :param plan:        (lst<BlockPlanEntry>) complete ordered playback plan
        :param block_title: (str) scheduled program title for status reporting
        """
        self.index = index
        self.offset = offset
        self.plan = plan
        self.block_title = block_title

    def __str__(self):
        """
        Format the program title, active entry index, offset, and plan length for diagnostics
        """
        return 'PlayPoint: title={0} index={1} offet={2} plan_len={3}'.format(self.block_title, self.index,
                                                                              self.offset, len(self.plan))


class LiquidManager(object):
    """
    Share loaded schedules and resolve broadcast times into player starting positions
    """
    __we_are_all_one = {}
    _initialized = False
    station_configs = []

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __init__(self):
        """
        Attach shared schedule state and load schedules on first initialization
        """
        self.__dict__ = self.__we_are_all_one
        if not self._initialized:
            self._initialized = True
            self.reload_schedules()

    def reload_schedules(self):
        """
        Refresh the shared station list and reload saved schedules for non-guide, non-streaming stations
        """
        self.station_configs = StationManager().stations
        self.schedules = {}
        for station in self.station_configs:
            if station['network_type'] != 'guide' and station['network_type'] != 'streaming':
                _id = station['network_name']
                self.schedules[_id] = liquid_api.get_blocks(station)

    def get_schedule_by_name(self, network_name):
        """
        Return a network's loaded blocks, or None when the network is absent
        """
        if network_name in self.schedules:
            return self.schedules[network_name]
        else:
            return None

    def reset_all_schedules(self):
        """
        Rewind pending episode sequences, delete supported station schedules, and reload the registry
        """
        for station_config in self.station_configs:
            if station_config['_has_schedule']:
                logging.getLogger('liquid').info('Deleting schedules for {}'.format(
                    station_config['network_name']))
                self.reset_sequences(station_config)
                liquid_api.delete_blocks(station_config)
        self.reload_schedules()

    def reset_schedule(self, station_config):
        """
        Rewind a station's pending sequences and delete its schedule before reloading all schedules
        """

        if station_config['_has_schedule']:
            logging.getLogger('liquid').info('Deleting schedules for {}'.format(station_config['network_name']))
            self.reset_sequences(station_config)
            liquid_api.delete_blocks(station_config)
        self.reload_schedules()

    def reset_sequences(self, station_config):
        """
        Rewind each pending sequence to its first scheduled episode from today onward

        :param station_config: (dict) station whose future sequence positions are being discarded
        """
        logging.getLogger('liquid').info('Resetting sequences for {}'.format(station_config['network_name']))
        # get the catalog
        catalog = ShowCatalog(station_config)

        _blocks = self.schedules.get(station_config['network_name'], [])

        now = datetime.datetime.now()
        today = datetime.datetime(now.year, now.month, now.day)
        _reaped = {}

        # make a sequence cache index
        all_seq_list = sequence_api.get_sequences_for_station(station_config)
        seq_index = {}
        for this_seq in all_seq_list:
            key = (this_seq.sequence_name, this_seq.tag_path)
            if key not in seq_index:
                seq_index[key] = this_seq

        for _block in _blocks:
            # are we to now yet?
            if _block.start_time >= today:
                # does it have a sequence and is that sequence in the catalog?

                if _block.sequence_key:
                    # make sure its in the store
                    #seq = SequenceAPI.get_sequence(
                    #    station_config, _block.sequence_key["sequence_name"], _block.sequence_key["tag_path"]
                    #)

                    # get the sequence from the index
                    skey = (_block.sequence_key['sequence_name'], _block.sequence_key['tag_path'])
                    seq = seq_index.get(skey, None)

                    # have we found it before?
                    if seq and skey not in _reaped:
                        # register that we found it
                        _reaped[skey] = _block
                        sequence_api.reset_by_episode_path(
                            station_config,
                            _block.sequence_key['sequence_name'],
                            _block.sequence_key['tag_path'],
                            _block.content.path,
                        )

        catalog._write_catalog()

    def get_extents(self, network_name):
        """
        Return the first start and last end time of a loaded station schedule

        :param network_name: (str) loaded network name
        :return:             (tuple) schedule boundaries, or two None values for an empty schedule
        :raises ValueError:  if the network has no loaded schedule entry
        """
        _id = network_name
        if _id not in self.schedules:
            raise (ValueError("Can't get extent for network named {} - it does not exist.".format(network_name)))
        _blocks = self.schedules[_id]
        if len(_blocks):
            return (_blocks[0].start_time, _blocks[-1].end_time)
        else:
            return (None, None)

    def get_summary(self):
        """
        Format the loaded networks' schedule boundaries as a multiline report
        """
        summary = ''
        for _id in self.schedules:
            (s, e) = self.get_extents(_id)
            summary += '{0} schedule extents: {1} to {2}\n'.format(_id, s, e)

        return summary

    def get_summary_json(self, network_name=None):
        """
        Serialize schedule boundaries for one network or all loaded networks

        :param network_name: (str) optional network name restricting the summary
        :return:             (obj) one summary dictionary or a list of summaries with ISO timestamps
        """
        if network_name:
            (s, e) = self.get_extents(network_name)
            return {
                'network_id': network_name,
                'start': s.isoformat() if s else None,
                'end': e.isoformat() if e else None
            }

        summaries = []
        for _id in self.schedules:
            (s, e) = self.get_extents(_id)
            summaries.append({
                'network_id': _id,
                'start': s.isoformat() if s else None,
                'end': e.isoformat() if e else None
            })

        return summaries

    def get_programming_block(self, network_name, when):
        """
        Find the loaded program containing the requested broadcast time

        :param network_name:              (str) network whose schedule should be searched
        :param when:                      (datetime) broadcast time to locate
        :return:                          (LiquidBlock) first block containing the time, or None for a gap
        :raises ScheduleNotFound:         if the loaded schedule is empty
        :raises ScheduleQueryNotInBounds: if the time lies outside the schedule boundaries
        """
        (start, end) = self.get_extents(network_name)

        # handle no schedule
        if start is None or end is None:
            raise ScheduleNotFound("Schedule doesn't exist for {}".format(network_name))
        # handle not in bounds
        elif start > when or end < when:
            raise ScheduleQueryNotInBounds(
                'Query for {0} programming at {1} failes because schedule is from {2} to {3}'.format(
                    network_name, when, start, end))
        # handle expected case
        else:
            # go through each block until we find the correct position (when > block start and < block end)
            for _block in self.schedules[network_name]:
                if when >= _block.start_time and when <= _block.end_time:
                    # this is it, no need to keep going
                    return _block

    def _build_stream_point(self, station_conf, when):
        """
        Build a playback plan from configured stream URLs starting at its first entry
        """
        # get the station conf

        # get an entry
        conf_streams = station_conf['streams']
        block_plan = []
        for stream in conf_streams:
            bpe = BlockPlanEntry(stream['url'], 0, stream['duration'], is_stream=True, content_type='stream',
                                 media_type=stream.get('media_type', 'video'))
            block_plan.append(bpe)

        pp = PlayPoint(0, 0, block_plan)
        return pp

    def get_play_point(self, network_name, when):
        """
        Locate the playback entry and elapsed offset for a station at a broadcast time

        :param network_name: (str) station to tune
        :param when:         (datetime) requested broadcast time
        :return:             (PlayPoint) active entry and offset, or None if no plan entry covers the time
        """
        station_conf = StationManager().station_by_name(network_name)
        if station_conf['network_type'] == 'streaming':
            return self._build_stream_point(station_conf, when)

        # get the block and get plan
        _block = self.get_programming_block(network_name, when)

        # find index in block plan
        found_index = 0
        current_mark = _block.start_time
        for entry in _block.plan:
            next_mark = current_mark + datetime.timedelta(seconds=entry.duration)
            if next_mark > when:
                # then this is the index - calc offset
                diff = when - current_mark
                return PlayPoint(found_index, diff.total_seconds(), _block.plan, _block.title)
            current_mark = next_mark
            found_index += 1

    def print_schedule(self, network_name, go_deep=False):
        """
        Log a station's blocks and optionally the timing of every playback segment

        :param network_name: (str) loaded station schedule to display
        :param go_deep:      (bool) whether to include individual plan entries and their start/end times
        """
        for _block in self.schedules[network_name]:
            _logger.info(_block)
            if go_deep:
                # print(_block)
                current_mark = _block.start_time
                next_mark = current_mark
                for _entry in _block.plan:
                    next_mark = current_mark + datetime.timedelta(seconds=_entry.duration)
                    _logger.info('{0} start={1} end={2}'.format(_entry, current_mark.time(), next_mark.time()))
                    current_mark = next_mark
