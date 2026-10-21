#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Project scheduled blocks into guide rows and time columns, resolving program titles and filling
stations without schedules with placeholders.
"""
import os
import sys
import json
import datetime

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.guide.guide_builder')

sys.path.append(os.getcwd())
from fs42.tools.media import metadata_io
from fs42.tools.media import title_parser
from fs42.core.station_manager import StationManager
from fs42.tools.schedule.liquid_manager import LiquidManager


def normalize_video_title(title):
    """
    Clean a media title using the server's custom filename patterns
    """
    custom_patterns = StationManager().server_conf.get('title_patterns', [])
    return title_parser.parse_title(title, custom_patterns)


def metadata_title_for_block(programming_block):
    """
    Read the cached display title for a single-media block, skipping clip collections
    """
    content = programming_block.content
    if content is None or isinstance(content, list):
        return None
    return metadata_io.pick_title(metadata_io.read(content.path))


class PreviewBlock(object):
    """
    Represent one guide cell with its duration and continuation flags
    """

    def __init__(self, title, width=1):
        """
        Store a guide title and initial cell width with continuation flags cleared

        :param title: (str) program title shown in the guide
        :param width: (float) cell width value; guide queries express it as visible seconds
        """
        self.title = title
        self.width = width
        self.started_earlier = False
        self.ends_later = False

    def __repr__(self):
        """
        Format a guide cell's title, width, and continuation flags for diagnostics
        """
        return '{0}: width={1} started={2} later={3}'.format(self.title, self.width, self.started_earlier,
                                                             self.ends_later)

    def to_json(self):
        """
        Serialize the guide cell's attributes as a JSON string
        """
        return json.dumps(self, default=lambda o: o.__dict__)


def query_slot(network_name, when, normalize):
    """
    Build program-preview cells spanning ninety minutes from the requested time

    :param network_name: (str) station whose loaded schedule should be queried
    :param when:         (datetime) beginning of the visible guide window
    :param normalize:    (bool) whether to clean titles when cached metadata has no title
    :return:             (lst<PreviewBlock>) cells with visible durations and continuation flags
    """
    start_marker = when
    current_marker = start_marker
    next_marker = start_marker
    end_target = start_marker + datetime.timedelta(hours=1, minutes=30)
    blocks = []
    keep_going = True

    while keep_going:
        programming_block = LiquidManager().get_programming_block(network_name, current_marker)

        total_duration = programming_block.playback_duration()
        remaining_duration = datetime.timedelta(seconds=total_duration)
        started_earlier = False
        ends_later = False
        if programming_block.start_time < start_marker:
            remaining_duration = programming_block.end_time - start_marker
            started_earlier = True

        next_marker = current_marker + remaining_duration + datetime.timedelta(seconds=1)

        if next_marker > end_target:
            ends_later = True

        _display_title = programming_block.title
        _meta_title = metadata_title_for_block(programming_block)

        if _meta_title:
            _display_title = _meta_title
        elif normalize:
            #normalize if explicitely told to
            _display_title = normalize_video_title(programming_block.title)

        _block = PreviewBlock(_display_title)
        _block.started_earlier = started_earlier
        _block.ends_later = ends_later
        _block.width = remaining_duration.total_seconds()
        blocks.append(_block)
        if next_marker > end_target:
            keep_going = False

        current_marker = next_marker

    return blocks


class GuideBuilder(object):
    """
    Build guide rows and time labels from active station schedules
    """

    def __init__(self, num_blocks=3, template_dir='fs42/tools/guide/templates/',
                 static_dir='fs42/tools/guide/static/'):
        """
        Store guide block-count and asset-directory settings

        :param num_blocks:   (int) configured number of guide time blocks
        :param template_dir: (str) guide template directory
        :param static_dir:   (str) guide static-asset directory
        """
        # ordered array of {"conf": station_config, "schedule": schedule}
        self.num_blocks = num_blocks
        self.template_dir = template_dir
        self.static_dir = static_dir

    def build_view(self, normalize=True):
        """
        Build a current ninety-minute guide view for visible stations

        Use station-name placeholders for unscheduled networks and an unavailable-data
        message when a station schedule cannot be queried.

        :param normalize: (bool) whether to clean program titles without metadata titles
        :return:          (dict) guide rows, station metadata, and half-hour time labels
        """
        view = {'rows': [], 'meta': []}

        now = datetime.datetime.now()
        hour = now.hour

        if now.minute > 30:
            past_half = True
            start_time = now.replace(minute=30, second=1, microsecond=0)
        else:
            past_half = False
            start_time = now.replace(minute=0, second=1, microsecond=0)

        # each statio is a row
        for station in StationManager().stations:
            if station['hidden']:
                continue
            elif not station['_has_schedule']:
                to_display = station.get('network_long_name', station['network_name'])
                placeholder = PreviewBlock(to_display, width=5400)
                entries = [placeholder]
            else:
                try:
                    entries = query_slot(station['network_name'], start_time, normalize)
                except Exception:
                    # Create a single block that spans the entire 1.5 hour viewing window (5400 seconds)
                    placeholder = PreviewBlock('No programming data available', width=5400)
                    entries = [placeholder]

            view['rows'].append(entries)
            network_name = station['network_name']
            channel_number = station['channel_number']
            view['meta'].append({'network_name': network_name, 'channel_number': channel_number})

        timings = []
        hour_one = hour
        hour_two = hour + 1

        if hour_two >= 24:
            hour_two = 0

        # TODO: this isn't an extendable approach - only supports 3 time blocks
        if past_half:
            timings.append('{}:30'.format(hour_one))
            timings.append('{}:00'.format(hour_two))
            timings.append('{}:30'.format(hour_two))
        else:
            timings.append('{}:00'.format(hour_one))
            timings.append('{}:30'.format(hour_one))
            timings.append('{}:00'.format(hour_two))

        formatted_timings = []
        time_format = StationManager().server_conf['time_format']
        for timing in timings:
            formatted = datetime.datetime.strptime(timing, '%H:%M').strftime(time_format)
            formatted_timings.append(formatted)

        view['timings'] = formatted_timings

        return view


if __name__ == '__main__':
    gb = GuideBuilder()
    blocks = gb.build_view()
    for block in blocks:
        _logger.info(block)
        _logger.info(blocks[block])
