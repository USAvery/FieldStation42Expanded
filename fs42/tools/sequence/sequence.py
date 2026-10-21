#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Represent named episode sequences and their entries, including configured playback ranges and
current positions.
"""
import math
import random
import logging


class SequenceEntry(object):
    """
    Identify one episode file in an ordered playback sequence
    """

    def __init__(self, fpath):
        """
        Store the episode's filesystem path as text
        """
        self.fpath = str(fpath)

    def __str__(self):
        """
        Format the episode path for sequence diagnostics
        """
        return 'SequenceEntry(fpath={})'.format(self.fpath)


class NamedSequence(object):
    """
    Track an ordered episode collection, its allowed range, and the next playback position
    """

    def __init__(self, station_name, sequence_name, tag_path, start_perc, end_perc, current_index, file_list,
                 initialized=False):
        """
        Initialize a station's named episode sequence and populate its sorted media list

        :param station_name:  (str) network owning the sequence
        :param sequence_name: (str) configured sequence identifier
        :param tag_path:      (str) content tag or child-show path
        :param start_perc:    (float) fractional starting boundary; negative selects a random initial episode
        :param end_perc:      (float) fractional exclusive ending boundary
        :param current_index: (int) saved episode position
        :param file_list:     (list) episode paths to sort and store
        :param initialized:   (bool) whether to preserve the saved position instead of choosing an initial one
        """
        self._l = logging.getLogger('{}'.format(self.__class__.__name__))
        self.station_name = station_name
        self.sequence_name = sequence_name
        self.tag_path = tag_path
        self.start_perc = start_perc
        self.end_perc = end_perc
        self.current_index = current_index
        self.initialized = initialized
        self.episodes = []  # Initialize episodes as an empty list
        self.start_index = 0
        self.end_index = 0
        self.populate(file_list)  # Populate episodes with the provided file list

    def __str__(self):
        """
        Format sequence identity, fractional boundaries, and current position for diagnostics
        """
        return 'NamedSequence(station={0}, sequence={1}, tag={2}, start={3}, end={4}, index={5})'.format(
            self.station_name, self.sequence_name, self.tag_path, self.start_perc, self.end_perc,
            self.current_index)

    def populate(self, file_list):
        """
        Sort episode paths and derive the playable range and initial position

        :param file_list: (list) episode paths replacing the current collection
        """
        self.episodes = []  # Reset the episodes list
        for file in file_list:
            entry = SequenceEntry(file)
            self.episodes.append(entry)

        # explicitely sort them by file path for alpha-numeric ordering:
        self.episodes = sorted(self.episodes, key=lambda entry: entry.fpath)

        # Clamp to the episode count - end_perc > 1 (misconfiguration) must not
        # push end_index past the last episode, or the completion check in
        # SequenceAPI.get_next_in_sequence can be skipped and cause an IndexError.
        self.end_index = min(
            math.floor(self.end_perc * (len(self.episodes))),
            len(self.episodes),
        )

        # start_index is derived from start_perc - recompute it on every load,
        # not just on first init, so loop-back / reset lands on the configured
        # start rather than 0. A negative start_perc means "start anywhere", so
        # the window opens at 0.
        if self.start_perc < 0:
            self.start_index = 0
        else:
            self.start_index = min(
                math.floor(self.start_perc * (len(self.episodes))),
                max(self.end_index - 1, 0),
            )

        if not self.initialized:
            try:
                if self.start_perc < 0:
                    self.current_index = random.randrange(self.start_index, self.end_index)
                else:
                    self.current_index = self.start_index
            except Exception as e:
                self._l.error('Error populating sequence - please check that you have the correct configuration')
                self._l.error('Current configuration for this sequence below:')
                self._l.error(str(self))
                if len(self.episodes) < 1:
                    self._l.error(
                        'The error is caused by not having any episodes in your sequence - check your tag path and sequence name'
                    )
                raise e
            self.initialized = True

    def get_series_length(self):
        """
        Return the length of the private episode collection
        """
        return len(self._episodes)
