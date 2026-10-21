#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build browser-rendered station bumps and next-up announcements. Encode their display options as URLs
and calculate durations for background-video loops.
"""
import os
import random
import subprocess
import urllib.parse

from fs42.tools.catalog import _constants
from fs42.core import logger as project_logger
from fs42.tools.catalog.catalog_entry import CatalogEntry

_logger = project_logger.setup('fs42.tools.catalog.autobump_agent')

base_url = 'http://127.0.0.1:4242/static/bump/bump.html'
url_prefix = ':autobump:='
tag_str = ':autobump:'


def do_fill(station_config):
    """
    Decide randomly whether to fill a break using the station's autobump probability
    """
    if 'autobump' not in station_config:
        return False
    if 'fill_break' not in station_config['autobump']:
        return False
    if random.random() < station_config['autobump']['fill_break']:
        return True
    return False


def fill_block(station_config, duration):
    """
    Create a countdown next-up bump lasting the requested number of seconds

    :param station_config: (dict) station settings containing autobump or off_air_autobump
    :param duration:       (float) length in seconds, also written into the selected bump settings
    :return:               (CatalogEntry) generated bump, or None when neither configuration exists
    """
    if 'autobump' in station_config:
        ab_config = station_config['autobump']
    elif 'off_air_autobump' in station_config:
        ab_config = station_config['off_air_autobump']
    else:
        return None

    ab_config['duration'] = duration
    fill_bump = next_up_bump(ab_config, base_url, station_config['network_name'], False, True)
    return fill_bump


def gen_bumps(station_config):
    """
    Create message and next-up bump entries from the station's autobump settings

    Fill in a missing duration from background-video loops, or use seven seconds.

    :param station_config: (dict) station settings whose autobump duration may be updated
    :return:               (dict) generated bump entries; disabled autobumps return empty start/end block values
    """
    if 'autobump' not in station_config:
        return {'start_block': None, 'end_block': None}

    ab_config = station_config['autobump']

    # first, check duration:
    # if the user set a duration, respect that as the bump length
    # otherwise, video-backed autobumps can use the video length as a default
    if 'duration' not in ab_config or not ab_config['duration']:
        if 'bg_video' in ab_config and ab_config['bg_video']:
            video_duration = get_bg_video_duration(ab_config['bg_video'])
            loop_count = get_bg_video_loop_count(ab_config)

            if video_duration:
                ab_config['duration'] = video_duration * loop_count
            else:
                ab_config['duration'] = 7
        else:
            ab_config['duration'] = 7

    msg_bump = message_bump(ab_config, base_url)
    next_bump = next_up_bump(ab_config, base_url, station_config['network_name'])
    return {'message_bump': msg_bump, 'next_bump': next_bump}


def is_autobump_url(url):
    """
    Check whether a catalog path carries the generated browser-bump URL prefix
    """
    return url.startswith(url_prefix)


def extract_url(prefixed_url):
    """
    Remove the internal autobump marker to obtain the browser URL
    """
    return prefixed_url.removeprefix(url_prefix)


def message_bump(ab_config, base_url, loopmusic=True, show_countdown=False):
    """
    Encode a station announcement as a browser-rendered catalog entry

    :param ab_config:      (dict) bump settings updated with music and countdown options
    :param base_url:       (str) address of the bump HTML page
    :param loopmusic:      (bool) whether background music should repeat
    :param show_countdown: (bool) whether the page should show remaining time
    :return:               (CatalogEntry) prefixed page URL and configured duration in seconds
    """
    ab_config['loopmusic'] = 'true' if loopmusic else 'false'
    ab_config['countdown'] = 'true' if show_countdown else 'false'
    if 'next_network' in ab_config:
        del ab_config['next_network']
    message_qs = generate_bump_query(ab_config)
    message_url = '{0}{1}?{2}'.format(url_prefix, base_url, message_qs)
    block = CatalogEntry(message_url, ab_config['duration'], tag_str)
    return block


def next_up_bump(ab_config, base_url, network_name, loopmusic=True, show_countdown=False):
    """
    Encode an upcoming-program announcement as a browser-rendered catalog entry

    :param ab_config:      (dict) bump settings updated with station subtitle and playback options
    :param base_url:       (str) address of the bump HTML page
    :param network_name:   (str) station whose upcoming programs the page should request
    :param loopmusic:      (bool) whether background music should repeat
    :param show_countdown: (bool) whether the page should show remaining time
    :return:               (CatalogEntry) prefixed page URL and configured duration in seconds
    """
    ab_config['subtitle'] = 'Coming up on {}'.format(network_name)
    ab_config['next_network'] = network_name
    ab_config['loopmusic'] = 'true' if loopmusic else 'false'
    ab_config['countdown'] = 'true' if show_countdown else 'false'
    message_qs = generate_bump_query(ab_config)
    message_url = '{0}{1}?{2}'.format(url_prefix, base_url, message_qs)
    block = CatalogEntry(message_url, ab_config['duration'], tag_str)
    return block


def get_bg_video_loop_count(config):
    """
    Read a positive background-video repeat count, falling back to one for invalid values
    """
    try:
        loop_count = int(config.get('bg_video_loop_count', 1))
        return max(loop_count, 1)
    except Exception:
        return 1


def get_bg_video_duration(bg_video):
    """
    Probe a local bump background video's duration in seconds, returning None on failure
    """
    if str(bg_video).startswith('http'):
        return None

    video_path = resolve_bg_video_path(bg_video)

    if not video_path or not os.path.exists(video_path):
        return None

    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of',
            'default=noprint_wrappers=1:nokey=1', video_path
        ], capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return None

        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except Exception:
        return None


def resolve_bg_video_path(bg_video):
    """
    Resolve a background-video filename against the working directory or bundled bump videos
    """
    # full paths can be probed directly
    if os.path.isabs(str(bg_video)):
        return bg_video

    # try the configured value relative to the current working directory
    if os.path.exists(bg_video):
        return bg_video

    # bare filenames are served from static/bump/video, similar to bg_music
    video_path = os.path.join(_constants.BUMP_VIDEO_DIR, str(bg_video))
    if os.path.exists(video_path):
        return video_path

    return None


def resolve_bg_video_url(bg_video):
    """
    Convert a relative background-video name into the local server's bump-video URL
    """
    if str(bg_video).startswith('http'):
        return bg_video

    # absolute URLs served from this FS42 instance can pass through
    if str(bg_video).startswith('/'):
        return bg_video

    # bare filenames are served from static/bump/video
    return 'http://127.0.0.1:4242/static/bump/video/{}'.format(bg_video)


def generate_bump_query(config):
    """
    Encode bump presentation settings as URL query parameters

    Require a title and include recognized text, color, background, animation, music,
    countdown, and upcoming-network options. Convert duration from seconds to
    milliseconds and expand relative media names into local server URLs.

    :param config:      (dict) bump settings, including title and optional duration in seconds
    :return:            (str) percent-encoded query string without a leading question mark
    :raises ValueError: if title is missing
    """
    if 'title' not in config:
        raise ValueError('title is required')

    params = {}

    # Map dictionary keys to URL parameter names
    key_mapping = {
        'title': 'title',
        'subtitle': 'subtitle',
        'variation': 'variation',
        'detail1': 'detail1',
        'detail2': 'detail2',
        'detail3': 'detail3',
        'bg_color': 'bg_color',
        'fg_color': 'fg_color',
        'bg': 'bg',
        'bg_video': 'bg_video',
        'bg_video_loop_count': 'bg_video_loop_count',
        'bg_video_audio': 'bg_video_audio',
        'text_position': 'text_position',
        'text_delay': 'text_delay',
        'text_fade_in': 'text_fade_in',
        'text_fade_out': 'text_fade_out',
        'text_hide_before_end': 'text_hide_before_end',
        'css': 'css',
        'next_network': 'next_network',
        'duration': 'duration',
        'bg_music': 'bg_music',
        'loopmusic': 'loopmusic',
        'countdown': 'countdown'
    }

    # Process each config item
    for key, url_param in key_mapping.items():
        if key in config and config[key] is not None:
            value = config[key]
            if key == 'duration':
                value = str(value * 1000)
            elif key == 'bg_music':
                # Convert filename to full URL if not already a URL
                if not str(value).startswith('http'):
                    value = 'http://127.0.0.1:4242/static/bump/music/{}'.format(value)
            elif key == 'bg_video':
                value = resolve_bg_video_url(value)
            elif key == 'bg_video_audio':
                value = str(value).lower()
            params[url_param] = value

    # Generate query string
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def main():
    """
    Test the generate_bump_query method with various configurations
    """

    # Test basic configuration
    basic_config = {'title': 'FSTV', 'subtitle': 'Field Station Television'}
    _logger.info('Basic config:')
    _logger.info('Query: {}'.format(generate_bump_query(basic_config)))
    _logger.info('')

    # Test retro variation with programming
    retro_config = {
        'title': 'FSTV',
        'subtitle': 'Field Station Television',
        'variation': 'retro',
        'next_network': 'Sitcomx',
        'duration': 10000,
    }
    _logger.info('Retro with programming:')
    _logger.info('Query: {}'.format(generate_bump_query(retro_config)))
    _logger.info('')

    # Test video background with explicit duration
    # this protects users from very long videos creating very long autobumps
    video_config = {
        'title': 'FSTV',
        'subtitle': 'Field Station Television',
        'variation': 'retro',
        'bg_video': 'example.webm',
        'bg_video_loop_count': 2,
        'bg_video_audio': True,
        'text_position': 'right',
        'text_delay': 1.5,
        'text_fade_in': 0.75,
        'text_fade_out': 0.5,
        'text_hide_before_end': 3,
        'duration': 12
    }
    _logger.info('Video background:')
    _logger.info('Query: {}'.format(generate_bump_query(video_config)))
    _logger.info('')

    # Test complete configuration
    complete_config = {
        'title': 'TESTTV',
        'subtitle': 'Test Broadcasting Network',
        'variation': 'modern',
        'detail1': 'Channel 42',
        'detail2': 'testtv.com',
        'detail3': '24/7 Testing',
        'bg_color': '#ff0000',
        'fg_color': '#ffffff',
        'next_network': 'Sitcomx',
        'duration': 15000
    }
    _logger.info('Complete configuration:')
    _logger.info('Query: {}'.format(generate_bump_query(complete_config)))
    _logger.info('')

    station_config = {'autobump': complete_config, 'network_name': 'Sitcomx'}

    _logger.info(message_bump(retro_config, base_url))
    _logger.info(next_up_bump(retro_config, base_url, 'Sitcomx'))
    generated_bumps = gen_bumps(station_config)
    _logger.info(generated_bumps)
    _logger.info(generated_bumps.get('message_bump', 'NONE'))
    _logger.info(generated_bumps.get('next_bump', 'NONE'))


if __name__ == '__main__':
    main()
