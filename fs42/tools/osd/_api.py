#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build status, logo, and volume displays from the OSD configuration file
"""
import os
import json

from fs42.core import logger as project_logger

from fs42.tools.osd._constants import CONFIG_FILE_PATH
from fs42.tools.osd._constants import LogoDisplayConfig
from fs42.tools.osd._constants import StatusDisplayConfig
from fs42.tools.osd._constants import VolumeDisplayConfig
from fs42.tools.osd.display.logo_display import LogoDisplay
from fs42.tools.osd.display.status_display import StatusDisplay
from fs42.tools.osd.display.volume_display import VolumeDisplay


_logger = project_logger.setup('fs42.tools.osd._api')


def load_objects():
    """
    Build display elements from the OSD configuration and ensure a volume meter exists

    Use a default status display when the configuration file is absent. Expand a
    HybridDisplay into separate logo and status elements; log unrecognized types.

    :return: (list) configured elements to update and draw in the OSD window
    """
    objects = []

    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_dict = json.load(f)
            for obj in config_dict:
                if 'type' not in obj:
                    obj['type'] = 'StatusDisplay'
                if obj['type'] == 'StatusDisplay':
                    del obj['type']
                    config = StatusDisplayConfig.model_validate(obj)
                    objects.append(StatusDisplay(config))
                elif obj['type'] == 'LogoDisplay':
                    del obj['type']
                    config = LogoDisplayConfig.model_validate(obj)
                    objects.append(LogoDisplay(config))
                elif obj['type'] == 'HybridDisplay':
                    del obj['type']
                    config_status = StatusDisplayConfig.model_validate(obj)
                    config_logo = LogoDisplayConfig.model_validate(obj)
                    status_osd = StatusDisplay(config_status)
                    status_logo = LogoDisplay(config_logo)
                    objects.append(status_logo)
                    objects.append(status_osd)
                elif obj['type'] == 'VolumeDisplay':
                    del obj['type']
                    config = VolumeDisplayConfig.model_validate(obj)
                    objects.append(VolumeDisplay(config))
                else:
                    _logger.info('Unrecognized osd object type: {}'.format(obj['type']))
    else:
        config = StatusDisplayConfig()
        objects.append(StatusDisplay(config))

    # Always show a volume meter unless one was explicitly configured. Match its
    # color to the first StatusDisplay so it blends with the rest of the OSD.
    if not any(isinstance(obj, VolumeDisplay) for obj in objects):
        volume_config = VolumeDisplayConfig()
        for obj in objects:
            if isinstance(obj, StatusDisplay):
                volume_config.color = obj.config.text_color
                break
        objects.append(VolumeDisplay(volume_config))

    return objects
