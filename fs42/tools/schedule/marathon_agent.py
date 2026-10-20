#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage marathon agent
"""
import random
import logging

from fs42.tools.schedule.schedule_hint import hint_klass_matcher

_l = logging.getLogger('MARATHONAGENT')


def detect_marathon(slot, when):
    """
    Detect marathon
    """
    if 'marathon' in slot and 'count' in slot['marathon']:
        marathon = slot['marathon']
    else:
        return False

    if 'chance' in marathon:
        #check if there is a date hint
        if 'hint' in marathon:
            hint_str = marathon['hint']
            hint_klass = hint_klass_matcher(hint_str)
            if hint_klass:
                hint_instance = hint_klass(hint_str)
                if not hint_instance.hint(when):
                    # there was a hint, but the time doesn't fit
                    return False
            else:
                _l.warning(
                    "Marathon hint '{}' doesn't match any hint type and will be ignored - this marathon is unrestricted"
                    .format(hint_str))

        if random.random() < marathon['chance']:
            return True

    return False


def fill_marathon(slot):
    """
    Fill marathon
    """
    buffer = []
    count = slot['marathon']['count']
    del slot['marathon']
    for _ in range(count - 1):
        buffer.append(slot)
    return buffer
