#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define display settings, content-type tags, status-file paths, and the fallback OSD font
"""
from dataclasses import field
from dataclasses import dataclass

from fs42.tools.osd.osd_layout import HAlignment
from fs42.tools.osd.osd_layout import VAlignment

SOCKET_FILE = 'runtime/play_status.socket'

VOLUME_SOCKET_FILE = 'runtime/volume.socket'

CONFIG_FILE_PATH = 'osd/osd.json'

DEFAULT_FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


class _DisplayConfig(object):
    """
    Normalize lightweight display settings without loading a general-purpose validation runtime
    """

    def __post_init__(self):
        """
        Convert JSON-compatible setting values and reject malformed display options
        """
        from fs42.tools.osd._utils import normalize_config
        normalize_config(self)


@dataclass
class LogoDisplayConfig(_DisplayConfig):
    """
    Define default logo placement, visibility timing, and fallback image settings
    """
    socket_file: str = SOCKET_FILE
    halign: HAlignment = HAlignment.RIGHT
    valign: VAlignment = VAlignment.TOP
    width: float = 0.112
    height: float = 0.15
    x_margin: float = 0.05
    y_margin: float = 0.05
    logo_mapping: dict[str, str] = field(default_factory=dict)
    default_logo: str | None = None
    always_show: bool = False
    display_time: float = 5.0
    default_show_logo: bool = True
    default_logo_permanent: bool = False
    default_logo_alpha: float = 1.0


@dataclass
class StatusDisplayConfig(_DisplayConfig):
    """
    Define the status file, text format, font, placement, and visibility duration
    """
    socket_file: str = SOCKET_FILE
    display_time: float = 2.0
    halign: HAlignment = HAlignment.LEFT
    valign: VAlignment = VAlignment.TOP
    format_text: str = '{channel_number} - {network_name}'
    text_color: tuple[int, int, int, int] = (0, 255, 0, 200)
    font_size: int = 40
    expansion_factor: float = 1.0
    font: str | None = None
    x_margin: float = 0.1
    y_margin: float = 0.1
    delay: float = 0.0


@dataclass
class VolumeDisplayConfig(_DisplayConfig):
    """
    Define volume-meter dimensions, color, edge spacing, and visibility duration
    """
    socket_file: str = VOLUME_SOCKET_FILE
    display_time: float = 5.0
    halign: HAlignment = HAlignment.CENTER
    valign: VAlignment = VAlignment.BOTTOM
    color: tuple[int, int, int, int] = (0, 255, 0, 200)
    width: float = 0.4
    height: float = 0.04
    x_margin: float = 0.1
    y_margin: float = 0.375
    border_thickness: float = 2.0
    padding: float = 0.008


class ContentType(object):
    """
    Name the player status tags used to distinguish programs, breaks, and special channels
    """
    FEATURE = 'feature'
    COMMERCIAL = 'commercial'
    BUMP = 'bump'
    SIGN_OFF = 'sign_off'
    OFF_AIR = 'off_air'
    GUIDE = 'guide'
    WEB = 'web'
    MUSIC = 'music'
    UNKNOWN = 'unknown'
