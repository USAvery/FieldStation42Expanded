#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage test metadata io
"""
from fs42.tools.media import metadata_io


class TestNormalize(object):
    """
    TestNormalize
    """

    def test_legacy_audio_row_gets_year_and_type(self):
        """
        Check legacy audio row gets year and type
        """
        # Rows written before normalization used `date` and had no `type`.
        legacy = {
            'title': 'Long Way Down',
            'artist': 'Robert DeLong',
            'album': 'Long Way Down',
            'date': '2014',
            'genre': 'Alternative Rock'
        }
        assert metadata_io.normalize(legacy) == {
            'title': 'Long Way Down',
            'artist': 'Robert DeLong',
            'album': 'Long Way Down',
            'year': '2014',
            'genre': 'Alternative Rock',
            'type': 'music',
        }

    def test_already_normalized_is_unchanged(self):
        """
        Check already normalized is unchanged
        """
        meta = {'type': 'movie', 'title': 'The Thing', 'year': '1982'}
        assert metadata_io.normalize(meta) == meta

    def test_year_wins_when_both_present(self):
        """
        Check year wins when both present
        """
        meta = metadata_io.normalize({'title': 'X', 'date': '2014', 'year': '2015'})
        assert meta['year'] == '2015'

    def test_does_not_mutate_input(self):
        """
        Check does not mutate input
        """
        original = {'title': 'X', 'date': '2014'}
        metadata_io.normalize(original)
        assert original == {'title': 'X', 'date': '2014'}

    def test_non_dict_passthrough(self):
        """
        Check non dict passthrough
        """
        assert metadata_io.normalize(None) is None
