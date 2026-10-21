#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define scheduling time units and calendar labels, and calculate the start of the next week or month.
"""
import calendar
import datetime

MONTHS = list(calendar.month_name)[1:]
OPERATING_HOURS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5]
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
HOUR2 = 7200
HOUR = 3600
H_HOUR = 1800
Q_HOUR = 900
MIN_10 = 600
MIN_5 = 300
MIN_3 = 180
MIN_2 = 120
MIN_1 = 60
MIN_0_5 = 30
HOUR_CONTENT_DURATION = 2640  # 44 minutes
H_HOUR_CONTENT_DURATION = 1320  # 22 minutes


def next_week(when):
    """
    Find the next Monday at the start of the broadcast day

    :param when: (datetime) date within the current week
    :return:     (datetime) naive datetime for the following Monday at 06:00
    """
    weekday = when.weekday()
    # go one day past the EOW (weekday is 0-6)
    eow = when + datetime.timedelta(days=(7 - weekday))
    return datetime.datetime(eow.year, eow.month, eow.day, hour=OPERATING_HOURS[0])


def next_month(when):
    """
    Find the first day of the next month at the start of the broadcast day

    :param when: (datetime) date within the current month
    :return:     (datetime) naive datetime for the following month's first day at 06:00
    """
    eom = (when.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    return datetime.datetime(eom.year, eom.month, eom.day, hour=OPERATING_HOURS[0])
