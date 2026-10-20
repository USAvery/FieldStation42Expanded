#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage test folder hints
"""
from datetime import datetime
from unittest.mock import patch

from fs42.core.station_io import StationIO
from fs42.tools.media import media_processor
from fs42.tools.schedule import schedule_hint
from fs42.core.station_manager import StationManager
from fs42.tools.schedule import schedule_hint as schedule_hint_utils


class TestFolderHints(object):
    """
    TestFolderHints
    """

    def setup_method(self):
        """
        Setup method
        """
        # reset the Borg singleton so each test starts clean
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
        config_data = {
            'server_port': 4242,
            'custom_holidays': {
                'aug_day': 'August 29',
                'thanksgiving': '4th thursday november'
            },
        }
        with patch.object(StationIO, 'load_main_config', return_value=config_data):
            with patch('fs42.core.station_io.glob.glob', return_value=[]):
                StationManager()

    def _hints_for(self, folder, bumpdir=False):
        """
        Hints for
        """
        hints = media_processor._process_hints('catalog/test/{}'.format(folder), 'tag', bumpdir=bumpdir)
        return sorted(type(hint).__name__ for hint in hints)

    def test_existing_folder_names_still_match(self):
        """
        Check existing folder names still match
        """
        assert self._hints_for('October') == ['MonthHint']
        assert self._hints_for('Q4') == ['QuarterHint']
        assert self._hints_for('December 1 - December 25') == ['RangeHint']
        assert self._hints_for('morning') == ['DayPartHint']
        assert self._hints_for('friday') == ['DayofWeekHint']

    def test_unhinted_folder_gets_nothing(self):
        """
        Check unhinted folder gets nothing
        """
        assert self._hints_for('cartoons') == []

    def test_bump_hint_only_applies_to_bump_dirs(self):
        """
        Check bump hint only applies to bump dirs
        """
        assert self._hints_for('pre') == []
        assert self._hints_for('pre', bumpdir=True) == ['BumpHint']

    def test_week_number_folder(self):
        """
        Check week number folder
        """
        assert self._hints_for('week number 44') == ['WeekNumberHint']
        # a bare number is not a week number - test_pattern stays strict
        assert self._hints_for('44') == []

    def test_custom_holiday_folder(self):
        """
        Check custom holiday folder
        """
        assert self._hints_for('aug_day') == ['CustomHolidayHint']
        assert self._hints_for('thanksgiving') == ['CustomHolidayHint']

    def test_custom_holiday_folder_is_case_sensitive(self):
        """
        Check custom holiday folder is case sensitive
        """
        # holiday names are matched against the config keys exactly
        assert self._hints_for('Aug_Day') == []

    def test_holiday_folder_restricts_by_date(self):
        """
        Check holiday folder restricts by date
        """
        (hint, ) = media_processor._process_hints('catalog/test/aug_day', 'tag')
        assert hint.hint(datetime(2026, 8, 29, 12))
        assert not hint.hint(datetime(2026, 8, 28, 12))

    def test_matching_folder_names_stack(self):
        """
        Check matching folder names stack
        """
        # every pattern that matches is applied, and _test_candidate_hints
        # requires all of them to pass
        StationManager().server_conf['custom_holidays']['October'] = 'October 5'
        assert self._hints_for('October') == ['CustomHolidayHint', 'MonthHint']


class TestHintJSONRoundTrip(object):
    """
    TestHintJSONRoundTrip
    """

    def setup_method(self):
        """
        Setup method
        """
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
        config_data = {'server_port': 4242, 'custom_holidays': {'aug_day': 'August 29'}}
        with patch.object(StationIO, 'load_main_config', return_value=config_data):
            with patch('fs42.core.station_io.glob.glob', return_value=[]):
                StationManager()

    def test_every_registered_type_round_trips(self):
        """
        Check every registered type round trips
        """
        originals = [
            schedule_hint.MonthHint('October'),
            schedule_hint.QuarterHint('Q4'),
            schedule_hint.RangeHint('December 1 - December 25'),
            schedule_hint.DayPartHint('morning'),
            schedule_hint.DayofWeekHint('friday'),
            schedule_hint.BumpHint('pre'),
            schedule_hint.WeekNumberHint('week number 44'),
            schedule_hint.CustomHolidayHint('aug_day'),
        ]
        assert len(originals) == len(schedule_hint.HINT_KLASS_BY_TYPE)

        for original in originals:
            as_json = original.to_json()
            klass = schedule_hint.HINT_KLASS_BY_TYPE[as_json['type']]
            rebuilt = schedule_hint.create_hint_from_json(klass, as_json)
            assert type(rebuilt) is type(original)
            assert rebuilt.to_json() == as_json

    def test_round_trip_preserves_matching(self):
        """
        Check round trip preserves matching
        """
        when_hits = datetime(2026, 8, 29, 12)
        when_misses = datetime(2026, 8, 28, 12)
        original = schedule_hint.CustomHolidayHint('aug_day')
        rebuilt = schedule_hint_utils._create_custom_holiday_from_json(original.to_json())
        assert rebuilt.hint(when_hits)
        assert not rebuilt.hint(when_misses)

    def test_unknown_type_is_skipped_not_fatal(self):
        """
        Check unknown type is skipped not fatal
        """
        assert schedule_hint.HINT_KLASS_BY_TYPE.get('not_a_real_type') is None
