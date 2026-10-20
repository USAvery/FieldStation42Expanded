#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage test hint agent
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from fs42.tools.catalog import hint_agent
from fs42.core.station_io import StationIO
from fs42.core.station_manager import StationManager
from fs42.tools.catalog.catalog_entry import CatalogEntry

# station_io normalizes meta_hint tags into content_dir relative paths before
# HintAgent ever sees them, so these are written in the post-normalized form
CONTENT_DIR = 'catalog/test'
SPECIAL = '{}/mix/special'.format(CONTENT_DIR)
GENERAL = '{}/mix/general'.format(CONTENT_DIR)

BOTH = ['mix/general', 'mix/special']
GENERAL_ONLY = ['mix/general']
SPECIAL_ONLY = ['mix/special']


class TestHintAgent(object):
    """
    TestHintAgent
    """

    def setup_method(self):
        """
        Setup method
        """
        # reset the Borg singleton so each test starts clean
        StationManager._StationManager__we_are_all_one = {}
        StationManager._initialized = False
        StationManager.stations = []
        self._make_manager({'aug_day': 'August 29', 'thanksgiving': '4th thursday november'})

    def _make_manager(self, custom_holidays):
        """
        Make manager
        """
        config_data = {'server_port': 4242, 'custom_holidays': custom_holidays}
        with patch.object(StationIO, 'load_main_config', return_value=config_data):
            with patch('fs42.core.station_io.glob.glob', return_value=[]):
                return StationManager()

    def _filter(self, meta_hints, when):
        """
        Filter
        """
        # entries are rebuilt every call - HintAgent caches its meta lookup on them
        candidates = [
            CatalogEntry('{}/one.mp4'.format(SPECIAL), 30, 'mix/special'),
            CatalogEntry('{}/two.mp4'.format(GENERAL), 30, 'mix/general'),
        ]
        kept = hint_agent.filter_candidate_entries(when, candidates, meta_hints)
        return sorted(entry.tag for entry in kept)

    def test_no_meta_hints_keeps_everything(self):
        """
        Check no meta hints keeps everything
        """
        assert self._filter([], datetime(2026, 3, 1, 12)) == BOTH

    def test_untagged_content_is_never_restricted(self):
        """
        Check untagged content is never restricted
        """
        # the hint covers mix/special, so mix/general is unaffected by it
        hints = [{'tags': [SPECIAL], 'custom_holiday': 'aug_day'}]
        assert self._filter(hints, datetime(2026, 1, 1, 12)) == GENERAL_ONLY

    def test_custom_holiday_fixed_date(self):
        """
        Check custom holiday fixed date
        """
        hints = [{'tags': [SPECIAL], 'custom_holiday': 'aug_day'}]
        # Aug 29 2026 is a Saturday, and a fixed date is taken literally
        assert self._filter(hints, datetime(2026, 8, 29, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 8, 28, 12)) == GENERAL_ONLY
        assert self._filter(hints, datetime(2026, 8, 30, 12)) == GENERAL_ONLY

    def test_custom_holiday_ordinal_date(self):
        """
        Check custom holiday ordinal date
        """
        hints = [{'tags': [SPECIAL], 'custom_holiday': 'thanksgiving'}]
        # 4th thursday of november 2026 is the 26th
        assert self._filter(hints, datetime(2026, 11, 26, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 11, 25, 12)) == GENERAL_ONLY

    def test_week_number(self):
        """
        Check week number
        """
        hints = [{'tags': [SPECIAL], 'week_number': 20}]
        # May 11 2026 is ISO week 20, May 18 is week 21
        assert self._filter(hints, datetime(2026, 5, 11, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 5, 18, 12)) == GENERAL_ONLY

    def test_week_number_accepts_every_value_form(self):
        """
        Check week number accepts every value form
        """
        for value in (20, '20', 'week number 20'):
            hints = [{'tags': [SPECIAL], 'week_number': value}]
            assert self._filter(hints, datetime(2026, 5, 11, 12)) == BOTH
            assert self._filter(hints, datetime(2026, 5, 18, 12)) == GENERAL_ONLY

    def test_month(self):
        """
        Check month
        """
        hints = [{'tags': [SPECIAL], 'month': 'October'}]
        assert self._filter(hints, datetime(2026, 10, 5, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 11, 5, 12)) == GENERAL_ONLY

    def test_month_is_case_tolerant(self):
        """
        Check month is case tolerant
        """
        # unlike a folder name, which has to be capitalized
        hints = [{'tags': [SPECIAL], 'month': 'october'}]
        assert self._filter(hints, datetime(2026, 10, 5, 12)) == BOTH

    def test_quarter(self):
        """
        Check quarter
        """
        hints = [{'tags': [SPECIAL], 'quarter': 'Q4'}]
        assert self._filter(hints, datetime(2026, 10, 5, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 5, 5, 12)) == GENERAL_ONLY

    def test_day_of_week(self):
        """
        Check day of week
        """
        hints = [{'tags': [SPECIAL], 'day_of_week': 'friday'}]
        # March 6 2026 is a Friday
        assert self._filter(hints, datetime(2026, 3, 6, 12)) == BOTH
        assert self._filter(hints, datetime(2026, 3, 7, 12)) == GENERAL_ONLY

    def test_day_of_week_is_case_tolerant(self):
        """
        Check day of week is case tolerant
        """
        # constructed directly here rather than gated by test_pattern first
        hints = [{'tags': [SPECIAL], 'day_of_week': 'Friday'}]
        assert self._filter(hints, datetime(2026, 3, 6, 12)) == BOTH

    def test_day_of_week_rejects_a_name_that_is_not_a_day(self):
        """
        Check day of week rejects a name that is not a day
        """
        hints = [{'tags': [SPECIAL], 'day_of_week': 'banana'}]
        with pytest.raises(ValueError, match='Day of week not valid'):
            self._filter(hints, datetime(2026, 3, 6, 12))

    def test_date_range(self):
        """
        Check date range
        """
        hints = [{'tags': [SPECIAL], 'date_range': 'December 1 - December 25'}]
        assert self._filter(hints, datetime(2025, 12, 10, 12)) == BOTH
        assert self._filter(hints, datetime(2025, 6, 10, 12)) == GENERAL_ONLY

    def test_day_part(self):
        """
        Check day part
        """
        hints = [{'tags': [SPECIAL], 'day_part': 'morning'}]
        assert self._filter(hints, datetime(2026, 3, 1, 7)) == BOTH
        assert self._filter(hints, datetime(2026, 3, 1, 20)) == GENERAL_ONLY

    def test_every_condition_in_an_entry_must_pass(self):
        """
        Check every condition in an entry must pass
        """
        hints = [{'tags': [SPECIAL], 'week_number': 20, 'day_part': 'morning'}]
        assert self._filter(hints, datetime(2026, 5, 11, 7)) == BOTH
        # right week, wrong day part
        assert self._filter(hints, datetime(2026, 5, 11, 20)) == GENERAL_ONLY
        # right day part, wrong week
        assert self._filter(hints, datetime(2026, 5, 18, 7)) == GENERAL_ONLY

    def test_exclusive_takes_over_the_pool(self):
        """
        Check exclusive takes over the pool
        """
        hints = [{'tags': [SPECIAL], 'custom_holiday': 'aug_day', 'exclusive': True}]
        assert self._filter(hints, datetime(2026, 8, 29, 12)) == SPECIAL_ONLY
        assert self._filter(hints, datetime(2026, 8, 28, 12)) == GENERAL_ONLY

    def test_unrecognized_key_is_not_a_condition(self):
        """
        Check unrecognized key is not a condition
        """
        # captures current behavior - an unknown field is ignored rather than
        # rejected, so the tag ends up unrestricted
        hints = [{'tags': [SPECIAL], 'not_a_hint': 'whatever'}]
        assert self._filter(hints, datetime(2026, 3, 1, 12)) == BOTH
