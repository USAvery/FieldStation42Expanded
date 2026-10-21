#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify temporal hint matching for week numbers, months, quarters, custom holidays, and date ranges.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from fs42.core.timings import MONTHS
from fs42.core.station_io import StationIO
from fs42.core.station_manager import StationManager
from fs42.tools.schedule.schedule_hint import MonthHint
from fs42.tools.schedule.schedule_hint import RangeHint
from fs42.tools.schedule.schedule_hint import QuarterHint
from fs42.tools.schedule.schedule_hint import WeekNumberHint
from fs42.tools.schedule.schedule_hint import CustomHolidayHint
from fs42.tools.schedule import schedule_hint as schedule_hint_utils


class TestWeekNumberHint(object):
    """
    Verify ISO week-number parsing and broadcast-date matching
    """

    def test_hint_week_1(self):
        """
        Check hint week 1
        """
        hint = WeekNumberHint('week number 1')
        assert hint.hint(datetime.fromisoformat('2025-12-29'))
        assert not hint.hint(datetime.fromisoformat('2027-01-02'))

    def test_hint_week_53(self):
        """
        Check hint week 53
        """
        hint = WeekNumberHint('week number 53')
        assert hint.hint(datetime.fromisoformat('2026-12-29'))
        assert not hint.hint(datetime.fromisoformat('2026-12-27'))

    def test_wrong_hint(self):
        """
        Check wrong hint
        """
        hint = WeekNumberHint('week number 2')
        assert not hint.hint(datetime.fromisoformat('2026-03-18'))

    def test_test_pattern(self):
        """
        Check test pattern
        """
        assert schedule_hint_utils._test_week_number_pattern('week number 2')
        assert schedule_hint_utils._test_week_number_pattern('Week Number 5')
        assert not schedule_hint_utils._test_week_number_pattern('week number 54')
        assert not schedule_hint_utils._test_week_number_pattern('aaaaa')
        assert not schedule_hint_utils._test_week_number_pattern('week number -10')


class TestMonthHint(object):
    """
    Verify named month hints match only their calendar month
    """

    def test_hint(self):
        """
        Check hint
        """
        hint = MonthHint('November')
        when = datetime.fromisoformat('1972-11-17')
        assert hint.hint(when)

    def test_wrong_hint(self):
        """
        Check wrong hint
        """
        hint = MonthHint('December')
        when = datetime.fromisoformat('1972-11-17')
        assert not hint.hint(when)

    def test_all_months(self):
        """
        Check all months
        """
        for month in MONTHS:
            hint = MonthHint(month)
            when = datetime.strptime(month, '%B')
            assert hint.hint(when)

    def test_test_pattern(self):
        """
        Check test pattern
        """
        assert not schedule_hint_utils._test_month_pattern('aaaa')
        assert schedule_hint_utils._test_month_pattern('July')
        assert schedule_hint_utils._test_month_pattern('November')


class TestQuarterHint(object):
    """
    Verify quarter syntax and three-month calendar matching
    """

    def test_quarter(self):
        """
        Check quarter
        """
        hint = QuarterHint('Q1')
        when = datetime.fromisoformat('2001-02-17')
        assert hint.hint(when)

    def test_wrong_quarters(self):
        """
        Check wrong quarters
        """
        hint = QuarterHint('Q4')
        when = datetime.fromisoformat('2011-05-13')
        assert not hint.hint(when)

    def test_wrong_parameter(self):
        """
        Check wrong parameter
        """
        with pytest.raises(ValueError):
            QuarterHint('Q5')
        with pytest.raises(ValueError):
            QuarterHint('p3')

    def test_test_pattern(self):
        """
        Check test pattern
        """
        assert not schedule_hint_utils._test_quarter_pattern('sq1d')
        assert not schedule_hint_utils._test_quarter_pattern('q2sd')
        assert not schedule_hint_utils._test_quarter_pattern('s2q3')
        assert schedule_hint_utils._test_quarter_pattern('q1')
        assert schedule_hint_utils._test_quarter_pattern('q3')


class TestCustomHolidayHint(object):
    """
    Verify fixed-date and ordinal-weekday custom holidays across calendar years
    """

    def setup_method(self):
        """
        Reset the shared station registry before each custom-holiday test
        """
        # reset the Borg singleton so each test starts clean
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []

    def _make_manager(self, custom_holidays):
        """
        Install test holiday definitions without loading real station files
        """
        config_data = {'server_port': 4242, 'custom_holidays': custom_holidays}
        with patch.object(StationIO, 'load_main_config', return_value=config_data):
            with patch('fs42.core.station_io.glob.glob', return_value=[]):
                return StationManager()

    def test_fixed_date_is_literal(self):
        """
        Check fixed date is literal
        """
        self._make_manager({'christmas': 'December 25'})
        hint = CustomHolidayHint('christmas')
        # Dec 25, 2025 is a Thursday
        assert hint.hint(datetime.fromisoformat('2025-12-25'))
        assert not hint.hint(datetime.fromisoformat('2025-12-24'))
        # Dec 25, 2027 is a Saturday - still the 25th, no shifting to the 24th
        assert hint.hint(datetime.fromisoformat('2027-12-25'))
        assert not hint.hint(datetime.fromisoformat('2027-12-24'))
        # Dec 25, 2021 is a Sunday - still the 25th, no shifting to the 26th
        assert hint.hint(datetime.fromisoformat('2021-12-25'))
        assert not hint.hint(datetime.fromisoformat('2021-12-26'))

    def test_fixed_date_across_year_boundary(self):
        """
        Check fixed date across year boundary
        """
        # the old weekend shift could push a date into an adjacent year, where the
        # month/day comparison then matched nothing at all
        self._make_manager({'newyears': 'January 1'})
        hint = CustomHolidayHint('newyears')
        # Jan 1, 2028 is a Saturday
        assert hint.hint(datetime.fromisoformat('2028-01-01'))
        assert not hint.hint(datetime.fromisoformat('2027-12-31'))

    def test_ordinal_holiday(self):
        """
        Check ordinal holiday
        """
        self._make_manager({'thanksgiving': '4th thursday november'})
        hint = CustomHolidayHint('thanksgiving')
        assert hint.hint(datetime.fromisoformat('2026-11-26'))
        assert not hint.hint(datetime.fromisoformat('2026-11-25'))

    def test_ordinal_uppercase(self):
        """
        Check ordinal uppercase
        """
        self._make_manager({'thanksgiving': '4th Thursday November'})
        hint = CustomHolidayHint('thanksgiving')
        assert hint.hint(datetime.fromisoformat('2026-11-26'))
        assert not hint.hint(datetime.fromisoformat('2026-11-25'))

    def test_last_weekday(self):
        """
        Check last weekday
        """
        self._make_manager({'memorial_day': 'last monday may'})
        hint = CustomHolidayHint('memorial_day')
        assert hint.hint(datetime.fromisoformat('2026-05-25'))
        assert not hint.hint(datetime.fromisoformat('2026-05-26'))

    def test_test_pattern(self):
        """
        Check test pattern
        """
        self._make_manager({'memorial_day': 'last monday may'})
        assert not schedule_hint_utils._test_custom_holiday_pattern('around memorial day')
        assert not schedule_hint_utils._test_custom_holiday_pattern('MeMoRiAl_DaY')
        assert schedule_hint_utils._test_custom_holiday_pattern('memorial_day')


class TestRangeHint(object):
    """
    Verify annual date intervals, including ranges that cross the year boundary
    """

    def test_range(self):
        """
        Check range
        """
        hint = RangeHint('December 1 - December 25')
        assert hint.hint(datetime.fromisoformat('2024-12-15'))
        assert not hint.hint(datetime.fromisoformat('2024-01-15'))

    def test_range_cross_year(self):
        """
        Check range cross year
        """
        hint = RangeHint('December 1 - January 31')
        assert hint.hint(datetime.fromisoformat('2024-12-15'))
        assert hint.hint(datetime.fromisoformat('2025-01-10'))
        assert hint.hint(datetime.fromisoformat('2024-01-10'))
        assert hint.hint(datetime.fromisoformat('1985-01-10'))
        assert not hint.hint(datetime.fromisoformat('2025-04-15'))
        assert not hint.hint(datetime.fromisoformat('2040-04-15'))
        assert not hint.hint(datetime.fromisoformat('1976-04-15'))

    def test_test_pattern(self):
        """
        Check test pattern
        """
        assert schedule_hint_utils._test_range_pattern('December 1 - December 25')
        assert schedule_hint_utils._test_range_pattern('November  11 - December  15')
        assert schedule_hint_utils._test_range_pattern(' June    1 - JULY 25    ')
        assert schedule_hint_utils._test_range_pattern('april 13 -  august 16')
        assert schedule_hint_utils._test_range_pattern('march 3   april 07')
        assert not schedule_hint_utils._test_range_pattern('October 42 - December 13')
        assert not schedule_hint_utils._test_range_pattern('December 32 - December 13')
        assert not schedule_hint_utils._test_range_pattern('ExtraStuff December 1 - December 25')
        assert not schedule_hint_utils._test_range_pattern('December 1 - December 25 and this stuff')
