#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Parse XML or plain-text NFO sidecars into metadata and display fields, and launch or close eligible
metadata overlays.
"""
import os
import logging

from fs42.tools.media._constants import MAX_NFO_LINES
from fs42.tools.media._constants import OVERLAY_TYPES
from fs42.tools.media._constants import _OVERLAY_DEFAULTS
from fs42.tools.media._constants import DEFAULT_SHOW_SECONDS

_logger = logging.getLogger('NFOAgent')


class NFOData(object):
    """
    Hold the ordered text lines used by the media-information overlay
    """

    def __init__(self, lines):
        """
        Store display lines with title, information, and description in positional order
        """
        self.lines = lines  # list of non-empty strings, up to MAX_NFO_LINES

    @property
    def title(self):
        """
        Return the first display line or an empty string
        """
        return self.lines[0] if self.lines else ''

    @property
    def info(self):
        """
        Return the second display line or an empty string
        """
        return self.lines[1] if len(self.lines) > 1 else ''

    @property
    def description(self):
        """
        Return the third display line or an empty string
        """
        return self.lines[2] if len(self.lines) > 2 else ''


def _load_overlay_config():
    """
    Merge recognized overlay settings from the station manager into display defaults
    """
    cfg = dict(_OVERLAY_DEFAULTS)
    try:
        from fs42.core.station_manager import StationManager
        main_conf = StationManager().server_conf
        overlay_conf = main_conf.get('overlay_conf', {})
        for key in _OVERLAY_DEFAULTS:
            if key in overlay_conf:
                cfg[key] = overlay_conf[key]
    except Exception as e:
        _logger.warning('Could not load overlay config from StationManager: {}'.format(e))
    return cfg


def parse_nfo_string(content):
    """
    Parse an NFO sidecar's contents into a normalized metadata dict

    Handles any Kodi-format XML root tag (musicvideo, movie,
    episodedetails, tvshow, plus a generic fallback for other tags) and a
    plain-text fallback for non-XML files. Returns a dict carrying a `type`
    discriminator, or None if nothing usable could be parsed.

    Empty string fields are dropped so the stored JSON stays tidy.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        # Not XML — fall back to plain text, one field per non-empty line.
        lines = [l.strip() for l in content.splitlines() if l.strip()][:MAX_NFO_LINES]
        if not lines:
            return None
        return {'type': 'plaintext', 'title': lines[0], 'lines': lines}

    def get(field):
        """
        Read trimmed text from a direct XML child, using an empty string when missing
        """
        el = root.find(field)
        return el.text.strip() if el is not None and el.text else ''

    def as_int(raw):
        """
        Convert digit-only metadata text to an integer and preserve other values
        """
        return int(raw) if raw.isdigit() else raw

    tag = root.tag
    if tag == 'musicvideo':
        meta = {
            'type': 'music',
            'title': get('title'),
            'artist': get('artist'),
            'album': get('album'),
            'year': get('year') or get('premiered')[:4],
            'genre': get('genre'),
        }
    elif tag == 'movie':
        meta = {
            'type': 'movie',
            'title': get('title'),
            'year': get('year') or get('premiered')[:4],
            'plot': get('plot') or get('outline'),
            'genre': get('genre'),
        }
    elif tag == 'episodedetails':
        meta = {
            'type': 'episode',
            'title': get('title'),
            'show_title': get('showtitle'),
            'season': as_int(get('season')),
            'episode': as_int(get('episode')),
            'aired': get('aired'),
            'plot': get('plot') or get('outline'),
        }
    elif tag == 'tvshow':
        meta = {
            'type': 'tvshow',
            'title': get('title'),
            'year': get('year') or get('premiered')[:4],
            'plot': get('plot') or get('outline'),
            'genre': get('genre'),
        }
    else:
        # Unknown/unsupported Kodi root tag — keep the title and any of the
        # common fields that happen to be present.
        title = get('title')
        if not title:
            return None
        meta = {'type': tag, 'title': title}
        for opt in ('year', 'plot', 'genre'):
            opt_value = get(opt)
            if opt_value:
                meta[opt] = opt_value

    # Drop empty-string fields; keep non-string values (e.g. int season).
    meta = {k: v for k, v in meta.items() if v != ''}

    # Require at least one real field beyond the type discriminator.
    return meta if len(meta) > 1 else None


def read_metadata_from_disk(file_path):
    """
    Read and parse the UTF-8 NFO sidecar beside a media file

    :param file_path: (str) media filename whose extension is replaced with .nfo
    :return:          (dict) parsed metadata, or None if the sidecar is absent, unreadable, or invalid
    """

    nfo_path = os.path.splitext(file_path)[0] + '.nfo'

    if not os.path.exists(nfo_path):
        return None

    try:
        with open(nfo_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        _logger.warning('Failed to read NFO file {0}: {1}'.format(nfo_path, e))
        return None

    meta = parse_nfo_string(content)
    if meta is None:
        _logger.warning('NFO file {} could not be parsed'.format(nfo_path))
    return meta


def overlay_lines(meta):
    """
    Select nonempty music or plaintext metadata lines for the compact overlay

    :param meta: (dict) normalized media metadata
    :return:     (list) display lines up to MAX_NFO_LINES, or None for unsupported or empty metadata
    """

    if not meta:
        return None

    meta_type = meta.get('type')
    if meta_type == 'music':
        ordered = [meta.get(k, '') for k in ('artist', 'title', 'album', 'year')]
        lines = [str(l) for l in ordered if l][:MAX_NFO_LINES]
        return lines or None
    if meta_type == 'plaintext':
        lines = [l for l in meta.get('lines', []) if l][:MAX_NFO_LINES]
        return lines or None
    return None


def display_fields(meta):
    """
    Map music, episode, movie, or plaintext metadata into three common display fields

    :param meta: (dict) normalized media metadata
    :return:     (dict) title, info, and description strings, or None if metadata is absent
    """

    if not meta:
        return None

    meta_type = meta.get('type')
    title = str(meta.get('title', ''))

    if meta_type == 'music':
        info = str(meta.get('artist', ''))
        description = str(meta.get('album', ''))
    elif meta_type == 'episode':
        info = str(meta.get('show_title', ''))
        description = str(meta.get('plot', ''))
    elif meta_type == 'plaintext':
        lines = meta.get('lines', [])
        if not title and lines:
            title = lines[0]
        info = lines[1] if len(lines) > 1 else ''
        description = lines[2] if len(lines) > 2 else ''
    else:  # movie, tvshow, generic
        info = str(meta.get('year', ''))
        description = str(meta.get('plot', ''))

    return {'title': title, 'info': info, 'description': description}


def show_overlay(nfo_data, play_duration=None, show_seconds=DEFAULT_SHOW_SECONDS):
    """
    Show the supplied media-information lines through the shared display service

    :param nfo_data:      (NFOData) display lines and title, or None to skip display
    :param play_duration: (float) media duration in seconds, or None for persistent display
    :param show_seconds:  (float) length of timed visibility periods in seconds
    :return:              (PanelHandle) presentation handle, or None if absent or startup fails
    """

    if nfo_data is None:
        return None
    try:
        overlay_cfg = _load_overlay_config()
        from fs42.tools.display.client import get_client
        panel = get_client().show('media_info', lines=nfo_data.lines, play_duration=play_duration,
                                    show_seconds=show_seconds, overlay_cfg=overlay_cfg)
        _logger.info("Media information shown: '{}'".format(nfo_data.title))
        return panel
    except Exception as e:
        _logger.error('Failed to start NFO overlay: {}'.format(e))
        return None


def close_overlay(panel):
    """
    Hide a media-information presentation without terminating the shared display service

    :param panel: (PanelHandle) presentation to close, or None when no panel was created
    """
    if panel is not None:
        panel.hide()
