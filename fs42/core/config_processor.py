#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expand station templates and date or week overrides into the scheduling slots consumed by catalog
and schedule builders.
"""
import copy
from datetime import datetime

from fs42.core import timings


class ConfigurationError(Exception):
    pass


overridable = [
    'start_bump',
    'end_bump',
    'bump_dir',
    'commercial_dir',
    'break_strategy',
    'sequence',
    'sequence_start',
    'sequence_end',
    'schedule_increment',
    'random_tags',
    'video_scramble_fx',
    'marathon',
]


def preprocess(conf):
    """
    Expand station templates and named overrides into concrete scheduling slots

    :param conf: (dict) station configuration to update in place
    :return:     (dict) the same configuration with weekly, date, and week slots expanded
    """
    # first, fill in templates
    processed = _process_templates(conf)
    processed = _process_strategy(processed)
    processed = _process_date_overrides(processed)
    processed = _process_week_overrides(processed)
    return processed


def _expand_slot_overrides(slot, slot_override_defs, network_name, where):
    """
    Apply a named slot override and remove its reference from the expanded slot

    Reject unknown overrides and fields that are not allowed to vary per slot.
    A slot without an override is returned unchanged; an overridden slot is copied.

    :param slot:               (dict) hourly scheduling slot, optionally containing overrides
    :param slot_override_defs: (dict) named collections of permitted slot settings
    :param network_name:       (str) station name to include in validation errors
    :param where:              (str) slot location to include in validation errors
    :return:                   (dict) slot with the named settings applied
    """
    if not isinstance(slot, dict):
        raise ConfigurationError('Slot {0} for {1} must be a slot object.'.format(where, network_name))

    if 'overrides' not in slot:
        return slot

    slot = dict(slot)
    o_key = slot['overrides']

    if o_key not in slot_override_defs:
        raise ConfigurationError("Slot {0} for {1} references a slot override '{2}' that doesn't exist.".format(
            where, network_name, o_key))

    or_def = slot_override_defs[o_key]
    for to_override in or_def:
        if to_override not in overridable:
            raise ConfigurationError(
                "Slot {0} for {1} tries to override '{2}' in '{3}', but only the following can be overridden: {4}".
                format(where, network_name, to_override, o_key, overridable))
        slot[to_override] = or_def[to_override]

    del slot['overrides']
    return slot


def _valid_date_key(date_key, section='date_overrides'):
    """
    Validate a month-and-day date or a pair of dates separated by ' - '

    :param date_key:            (str) date expression such as January 01 - January 07
    :param section:             (str) configuration section to identify in error messages
    :return:                    (bool) True when each date parses successfully
    :raises ConfigurationError: if the expression contains an invalid date
    """
    # validate that this looks like either "Month Day" or "Month Day - Month Day"
    # raises ConfigurationError with helpful message on failure
    parts = [part.strip() for part in date_key.split(' - ')]

    if len(parts) not in (1, 2):
        raise ConfigurationError(
            "Invalid {0} key '{1}'. Expected format 'Month Day' or 'Month Day - Month Day'.".format(
                section, date_key))

    for part in parts:
        try:
            datetime.strptime(part, '%B %d')
        except ValueError:
            raise ConfigurationError(
                "Invalid date '{0}' in {1} key '{2}'. Ensure the day exists for the given month (e.g., April has 30 days)."
                .format(part, section, date_key))

    return True


def _process_templates(conf):
    """
    Replace weekday template names with independent copies of their hourly slots

    :param conf: (dict) station configuration to update in place
    :return:     (dict) configuration with weekday templates expanded
    """
    # first, see if there are templates
    if 'day_templates' not in conf:
        return conf

    templates = conf['day_templates']

    # now, go through each day:
    for day_key in timings.DAYS:
        if day_key not in conf:
            raise ConfigurationError(
                '{0} not found in config for {1} - requires an entry for each day of the week.'.format(
                    day_key, conf['network_name']))

        if isinstance(conf[day_key], str):
            # found a potential reference, so see if it exists
            ref_key = conf[day_key]
            if ref_key not in templates:
                raise ConfigurationError(
                    "Schedule for {0} references a template for {1} on {2}, but that template doesn't exist.".
                    format(conf['network_name'], ref_key, day_key))
            # then just inline it :) - copied, so later processing doesn't
            # rewrite the shared template and leak into everything else using it
            conf[day_key] = copy.deepcopy(templates[ref_key])

    return conf


def _process_date_overrides(conf):
    """
    Validate date-specific schedules and expand their templates and slot overrides

    :param conf: (dict) station configuration to update in place
    :return:     (dict) configuration with concrete hourly slots for each date override
    """
    if 'date_overrides' not in conf:
        return conf

    overrides = conf['date_overrides']

    if not isinstance(overrides, dict):
        raise ConfigurationError(
            'date_overrides for {} must be an object mapping dates to slot definitions.'.format(
                conf['network_name']))

    processed_overrides = {}

    for date_key, override_value in overrides.items():
        # validate date key (will raise ConfigurationError if invalid)
        _valid_date_key(date_key)

        if isinstance(override_value, str):
            template_key = override_value

            if 'day_templates' not in conf or template_key not in conf['day_templates']:
                raise ConfigurationError(
                    "date_overrides entry '{0}' for {1} references template '{2}', but that template doesn't exist."
                    .format(date_key, conf['network_name'], template_key))

            override_value = copy.deepcopy(conf['day_templates'][template_key])

        elif not isinstance(override_value, dict):
            raise ConfigurationError(
                "date_overrides entry '{0}' for {1} must be either a day template reference or an object of hourly slots."
                .format(date_key, conf['network_name']))

        processed_overrides[date_key] = {
            hour_key:
            _expand_slot_overrides(
                slot,
                conf.get('slot_overrides', {}),
                conf['network_name'],
                "in date_overrides '{0}' at hour {1}".format(date_key, hour_key),
            )
            for hour_key, slot in override_value.items()
        }

    conf['date_overrides'] = processed_overrides
    return conf


def _process_week_overrides(conf):
    """
    Expand weekday schedules within each date-bounded week override

    :param conf: (dict) station configuration to update in place
    :return:     (dict) configuration with validated weekday names and expanded slots
    """
    if 'week_overrides' not in conf:
        return conf

    overrides = conf['week_overrides']

    if not isinstance(overrides, dict):
        raise ConfigurationError(
            'week_overrides for {} must be an object mapping date ranges to week schedules.'.format(
                conf['network_name']))

    templates = conf.get('day_templates', {})
    slot_override_defs = conf.get('slot_overrides', {})

    processed_overrides = {}

    for date_key, week_schedule in overrides.items():
        _valid_date_key(date_key, section='week_overrides')

        if not isinstance(week_schedule, dict):
            raise ConfigurationError("week_overrides entry '{0}' for {1} must be an object with day keys.".format(
                date_key, conf['network_name']))

        # catch typo'd/capitalized day names rather than silently dropping them
        for present_key in week_schedule:
            if present_key not in timings.DAYS:
                raise ConfigurationError(
                    "week_overrides entry '{0}' for {1} has unknown day key '{2}' - expected one of: {3}".format(
                        date_key, conf['network_name'], present_key, timings.DAYS))

        processed_week = {}
        for day_key in timings.DAYS:
            if day_key not in week_schedule:
                continue

            day_val = week_schedule[day_key]

            if isinstance(day_val, str):
                if day_val not in templates:
                    raise ConfigurationError(
                        "week_overrides entry '{0}' on {1} for {2} references template '{3}', but that template doesn't exist."
                        .format(date_key, day_key, conf['network_name'], day_val))
                day_val = templates[day_val]
            elif not isinstance(day_val, dict):
                raise ConfigurationError(
                    "week_overrides entry '{0}' on {1} for {2} must be a day template reference or an object of hourly slots."
                    .format(date_key, day_key, conf['network_name']))

            processed_week[day_key] = {
                hour_key:
                _expand_slot_overrides(
                    slot,
                    slot_override_defs,
                    conf['network_name'],
                    "in week_overrides '{0}' on {1} at hour {2}".format(date_key, day_key, hour_key),
                )
                for hour_key, slot in day_val.items()
            }

        processed_overrides[date_key] = processed_week

    conf['week_overrides'] = processed_overrides
    return conf


def _process_strategy(conf):
    """
    Apply named slot overrides throughout the station's regular weekly schedule

    :param conf: (dict) station configuration to update in place
    :return:     (dict) configuration containing the expanded weekly slots
    """
    if 'slot_overrides' not in conf:
        return conf

    overrides = conf['slot_overrides']

    for day_key in timings.DAYS:
        for hour_key in list(conf[day_key]):
            conf[day_key][hour_key] = _expand_slot_overrides(
                conf[day_key][hour_key],
                overrides,
                conf['network_name'],
                'on {0} at hour {1}'.format(day_key, hour_key),
            )

    return conf
