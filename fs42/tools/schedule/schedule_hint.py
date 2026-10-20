#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage schedule hint
"""
import re
from datetime import datetime
from datetime import timedelta

from fs42.core import timings
from fs42.core import station_manager


def _test_temporal_pattern(to_test):
    """
    Check pattern
    """
    pass


def _test_dayof_week_pattern(to_test):
    """
    Check pattern
    """
    return to_test in timings.DAYS


def _create_dayof_week_from_json(json_data):
    """
    FromJSON
    """
    return DayofWeekHint(json_data['day'])


def _test_day_part_pattern(to_test):
    """
    Check pattern
    """
    return to_test in station_manager.StationManager().get_day_parts().keys()


def _create_day_part_from_json(json_data):
    """
    FromJSON
    """
    return DayPartHint(json_data['part'])


def _test_bump_pattern(to_test):
    """
    Check pattern
    """
    return to_test == BumpHint.pre or to_test == BumpHint.post


def _create_bump_from_json(json_data):
    """
    FromJSON
    """
    return BumpHint(json_data['where'])


# accepts 20, "20" and "week number 20"
def _parse_week_number(value):
    """
    Parse
    """
    as_text = str(value).strip()
    m = WeekNumberHint.pattern.match(as_text) or WeekNumberHint.bare_pattern.match(as_text)
    if m is None:
        raise ValueError("Week number not valid: {0!r} - should be 1-53 or 'week number <1-53>'".format(value))
    return int(m.group(1))


def _test_week_number_pattern(to_test):
    """
    Check pattern
    """
    if not isinstance(to_test, str):
        return False
    m = WeekNumberHint.pattern.match(to_test)
    a = False if m is None else True
    return a


def _create_week_number_from_json(json_data):
    """
    FromJSON
    """
    return WeekNumberHint(json_data['week_number'])


def _test_month_pattern(to_test):
    """
    Check pattern
    """
    return to_test in timings.MONTHS


def _create_month_from_json(json_data):
    """
    FromJSON
    """
    return MonthHint(json_data['month'])


def _test_quarter_pattern(to_test):
    """
    Check pattern
    """
    m = QuarterHint.pattern.match(to_test)
    a = False if m is None else True
    return a


def _create_quarter_from_json(json_data):
    """
    FromJSON
    """
    return QuarterHint(json_data['quarter'])


def _test_custom_holiday_pattern(to_test):
    """
    Check pattern
    """
    return to_test in station_manager.StationManager().get_custom_holidays().keys()


def _create_custom_holiday_from_json(json_data):
    """
    FromJSON
    """
    return CustomHolidayHint(json_data['custom_holiday'])


def _scrape_range_dates(m):
    """
    Scrape dates
    """
    # this WILL throw a value error if not valid date ranges
    start = datetime.strptime('{0} {1:0>2}'.format(m.group(1).capitalize(), m.group(2)), '%B %d')
    end = datetime.strptime('{0} {1:0>2}'.format(m.group(3).capitalize(), m.group(4)), '%B %d')
    return (start, end)


def _test_range_pattern(to_test):
    """
    Check pattern
    """
    m = RangeHint.pattern.match(to_test)
    a = False if m is None else True
    if a:
        # check that it can be a valid date
        try:
            (start, end) = _scrape_range_dates(m)
        except ValueError:
            a = False
    return a


def _create_range_from_json(json_data):
    """
    FromJSON
    """
    return RangeHint('{}'.format(json_data['range_string']))


# all temporal hints should implement this interface
class TemporalHint(object):
    """
    TemporalHint
    """

    def __init__(self):
        """
        Initialize the instance
        """
        pass

    # when is a datetime object for the time slot
    def hint(self, when):
        """
        Hint
        """
        return True


class DayofWeekHint(object):
    """
    DayofWeekHint
    """

    def __init__(self, day_name):
        """
        Initialize the instance
        """
        self.day_name = str(day_name).strip().lower()
        if self.day_name not in timings.DAYS:
            raise ValueError('Day of week not valid: {0!r} - should be one of: {1}'.format(
                day_name, ', '.join(timings.DAYS)))
        self.type = 'day_of_week'

    def hint(self, when):
        """
        Hint
        """
        return when.strftime('%A').lower() == self.day_name

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'day': self.day_name}


class DayPartHint(object):
    """
    DayPartHint
    """

    def __init__(self, part_name):
        """
        Initialize the instance
        """
        self.part_name = part_name
        self.type = 'day_part'

    def hint(self, when):
        """
        Hint
        """
        return when.hour in station_manager.StationManager().get_day_parts()[self.part_name]

    def __str__(self):
        """
        Get the display text
        """
        return '{}'.format(self.part_name)

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'part': self.part_name}


class BumpHint(object):
    """
    BumpHint
    """
    pre = 'pre'
    post = 'post'

    def __init__(self, where='pre'):
        """
        Initialize the instance
        """
        self.where = where
        self.type = 'bump'

    def hint(self, when):
        """
        Hint
        """
        # always return true, since it doesn't really matter when
        return True

    def __str__(self):
        """
        Get the display text
        """
        return 'bump:{}'.format(self.where)

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'where': self.where}


class WeekNumberHint(object):
    """
    WeekNumberHint
    """
    pattern = re.compile('^week number ([1-9]|[1-4][0-9]|5[0-3])$', re.IGNORECASE)
    # meta_hints name the field explicitly, so they pass the number on its own
    bare_pattern = re.compile('^([1-9]|[1-4][0-9]|5[0-3])$')

    def __init__(self, week_name):
        """
        Initialize the instance
        """
        self.week_number = _parse_week_number(week_name)
        self.week_name = 'week number {}'.format(self.week_number)
        self.type = 'week_number'

    # when should be a datetime object
    def hint(self, when):
        """
        Hint
        """
        return when.isocalendar().week == self.week_number

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'week_number': self.week_name}


class MonthHint(object):
    """
    MonthHint
    """

    def __init__(self, month_name):
        """
        Initialize the instance
        """
        self.month_name = month_name
        self.month_number = datetime.strptime(self.month_name, '%B').month
        self.type = 'month'

    # when should be a datetime object
    def hint(self, when):
        """
        Hint
        """
        return when.month == self.month_number

    def __str__(self):
        """
        Get the display text
        """
        return self.month_name

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'month': self.month_name}


class QuarterHint(object):
    """
    QuarterHint
    """
    pattern = re.compile('^[q|Q][1-4]$')

    def __init__(self, quarter_name):
        """
        Initialize the instance
        """
        self.quarter_name = quarter_name.lower()
        self.quarter = 0
        if _test_quarter_pattern(quarter_name):
            self.quarter = int(self.quarter_name.strip('Qq'))
        else:
            # this should be a runtime error
            raise ValueError('Quarter name not valid: {quarter_name}- should be one of Q1-Q4 or q1-q4')
        self.type = 'quarter'

    # when should be a datetime object
    def hint(self, when):
        """
        Hint
        """
        return (when.month - 1) // 3 + 1 == self.quarter

    def __str__(self):
        """
        Get the display text
        """
        return self.quarter_name

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'quarter': self.quarter_name}


class CustomHolidayHint(object):
    """
    CustomHolidayHint
    """
    fixed_pattern = re.compile('^ *({}) *([0-3]?[0-9])$'.format('|'.join(timings.MONTHS)), re.IGNORECASE)
    ordinal_pattern = re.compile(
        '^(1st|2nd|3rd|4th|last) ({0}) ({1})$'.format('|'.join(timings.DAYS), '|'.join(timings.MONTHS)),
        re.IGNORECASE)

    def __init__(self, holiday_name):
        """
        Initialize the instance
        """
        self.holiday_name = holiday_name

        # grab config from the station_manager
        if _test_custom_holiday_pattern(holiday_name):
            holiday_conf_str = station_manager.StationManager().get_custom_holidays().get(holiday_name)
        else:
            raise ValueError('Custom Holiday: {} not found in main config'.format(holiday_name))

        fixed_m = CustomHolidayHint.fixed_pattern.match(holiday_conf_str)
        ordinal_m = CustomHolidayHint.ordinal_pattern.match(holiday_conf_str)

        self.month = None
        self.day = None
        self.weekday_str = None
        self.n = None

        if fixed_m:
            self.month = fixed_m.group(1).capitalize()
            self.day = int(fixed_m.group(2))
        elif ordinal_m:
            self.month = ordinal_m.group(3).capitalize()
            self.weekday_str = ordinal_m.group(2).lower()
            self.n = -1 if not ordinal_m.group(1)[0].isdigit() else int(ordinal_m.group(1)[0])

        else:
            raise ValueError('Custom Holiday: {} date string not valid.'.format(holiday_name))

        self.type = 'custom_holiday'

    def hint(self, when):
        """
        Hint
        """
        year = when.year
        if self.day:
            # a fixed date means that date - no shifting off the weekend
            calc_date = datetime.strptime('{0} {1} {2}'.format(year, self.month, self.day), '%Y %B %d')
        elif self.weekday_str:
            raw_date = datetime.strptime('{0} {1} 1'.format(year, self.month), '%Y %B %d')
            calc_date = self._nth_weekday(raw_date, self.weekday_str, self.n)
        else:
            # left for expansion
            # raise error in case we find ourselves here
            raise ValueError('Custom Holiday: {} configuration read error.'.format(self.holiday_name))

        return calc_date.day == when.day and calc_date.month == when.month

    def _nth_weekday(self, month, weekday_str, n):
        """
        Nth weekday
        """
        # Assumes month is a datetime set to the 1st of the month.
        # Find the offset from the first
        weekday = timings.DAYS.index(weekday_str.lower())
        offset = (weekday - month.weekday()) % 7
        last_day = self._find_last_day(month)
        if n >= 0:
            day = 1 + offset + (n - 1) * 7
            return month.replace(day=day)
        else:
            return last_day - timedelta(days=(last_day.weekday() - weekday) % 7)

    def _find_last_day(self, when):
        """
        Find last day
        """
        if when.month == 12:
            next_first = when.replace(year=when.year + 1, month=1, day=1)
        else:
            next_first = when.replace(month=when.month + 1, day=1)
        return next_first - timedelta(days=1)

    def to_json(self):
        """
        ToJSON
        """
        return {'type': self.type, 'custom_holiday': self.holiday_name}


class RangeHint(object):
    """
    RangeHint
    """
    # matches patterns like: December 1 - December 25
    pattern = re.compile(
        '^ *({0}) *([0-3]?[0-9]) *-? *({1}) *([0-3]?[0-9]) *$'.format('|'.join(timings.MONTHS),
                                                                      '|'.join(timings.MONTHS)),
        re.IGNORECASE,
    )

    def __init__(self, range_string):
        """
        Initialize the instance
        """
        self.start_date = None
        self.end_date = None
        self.range_string = range_string
        if _test_range_pattern(range_string):
            m = RangeHint.pattern.match(range_string)
            try:
                (self.start_date, self.end_date) = _scrape_range_dates(m)

            except ValueError:
                # this should be a runtime error
                raise ValueError('Date range not valid - should be of form: December 1 - December 25')
        self.type = 'range'

    def hint(self, when):
        """
        Hint
        """
        # lets put stuff in the current years context first

        test_start = self.start_date
        test_end = self.end_date

        # this will only consider month and day, since the years are the same
        if self.start_date > self.end_date:
            # Crosses year boundary: something like Nov 15 - Jan 15
            if test_start.replace(year=when.year) <= when:
                # scenario 1: we are past the start date, like Nov 20
                test_start = test_start.replace(year=when.year)
                test_end = test_end.replace(year=when.year + 1)
            else:
                # scenario 2: we are before the start date - like Jan 15
                test_start = test_start.replace(year=when.year - 1)
                test_end = test_end.replace(year=when.year)
        else:
            # the simple case - they are both in the current year

            test_start = test_start.replace(year=when.year)
            test_end = test_end.replace(year=when.year)

        if test_start <= when and test_end >= when:
            return True
        else:
            return False

    def __str__(self):
        """
        Get the display text
        """
        return 'range_hint'

    def to_json(self):
        """
        ToJSON
        """
        return {
            'type': self.type,
            'range_string': self.range_string,
        }


MARATHON_HINT_KLASSES = [
    MonthHint,
    QuarterHint,
    RangeHint,
    DayofWeekHint,
    WeekNumberHint,
    CustomHolidayHint,
]

FOLDER_HINT_KLASSES = MARATHON_HINT_KLASSES + [DayPartHint]

META_HINT_KEYS = {
    'month': MonthHint,
    'quarter': QuarterHint,
    'date_range': RangeHint,
    'week_number': WeekNumberHint,
    'day_of_week': DayofWeekHint,
    'day_part': DayPartHint,
    'custom_holiday': CustomHolidayHint,
}

HINT_KLASS_BY_TYPE = {
    'month': MonthHint,
    'quarter': QuarterHint,
    'range': RangeHint,
    'day_part': DayPartHint,
    'day_of_week': DayofWeekHint,
    'bump': BumpHint,
    'week_number': WeekNumberHint,
    'custom_holiday': CustomHolidayHint,
}


def hint_klass_matcher(to_test, klasses=MARATHON_HINT_KLASSES):
    """
    Hint klass matcher
    """
    for klass in klasses:
        if test_pattern(klass, to_test):
            return klass
    return None


def test_pattern(hint_class, value):
    """
    Check pattern
    """
    return PATTERN_TESTS[hint_class](value)


def create_hint_from_json(hint_class, data):
    """
    Create hint from json
    """
    return JSON_FACTORIES[hint_class](data)


PATTERN_TESTS = {
    TemporalHint: _test_temporal_pattern,
    DayofWeekHint: _test_dayof_week_pattern,
    DayPartHint: _test_day_part_pattern,
    BumpHint: _test_bump_pattern,
    WeekNumberHint: _test_week_number_pattern,
    MonthHint: _test_month_pattern,
    QuarterHint: _test_quarter_pattern,
    CustomHolidayHint: _test_custom_holiday_pattern,
    RangeHint: _test_range_pattern
}

JSON_FACTORIES = {
    DayofWeekHint: _create_dayof_week_from_json,
    DayPartHint: _create_day_part_from_json,
    BumpHint: _create_bump_from_json,
    WeekNumberHint: _create_week_number_from_json,
    MonthHint: _create_month_from_json,
    QuarterHint: _create_quarter_from_json,
    CustomHolidayHint: _create_custom_holiday_from_json,
    RangeHint: _create_range_from_json
}
