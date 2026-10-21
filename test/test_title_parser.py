#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify filename-to-title normalization across episode formats, movie numbering, separators,
capitalization, and custom pattern precedence.
"""
import pytest

from fs42.tools.media import title_parser


class TestTitleParser(object):
    """
    Verify media filenames normalize to readable titles without losing expected acronyms
    """

    def test_title_parser_no_title(self):
        """
        Check title parser no title
        """
        episode = ''

        assert title_parser.parse_title(episode) == ''

    def test_title_parser_group_title_episode(self):
        """
        Check title parser group title episode
        """
        episode = '[Releasers] - Buffy the Vampire Slayer - 6'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_episode_pattern_separated(self):
        """
        Check title parser episode pattern separated
        """
        episode = 'Buffy the Vampire Slayer - s6-e7 - Once More, with Feeling'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_episode_pattern_together(self):
        """
        Check title parser episode pattern together
        """
        episode = 'Buffy the Vampire Slayer - S06E07 - Once More, with Feeling'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_episode_pattern_cross(self):
        """
        Check title parser episode pattern cross
        """
        episode = 'Buffy the Vampire Slayer - 06x7 - Once More, with Feeling'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_version_volume_format(self):
        """
        Check title parser version volume format
        """
        episode = 'Buffy the Vampire Slayer - V1-0003'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_simple_episode_numbers(self):
        """
        Check title parser simple episode numbers
        """
        episode = 'Buffy the Vampire Slayer - 07 - Once More, with Feeling'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_just_title(self):
        """
        Check title parser just title
        """
        episode = 'Buffy the Vampire Slayer'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_just_title_with_nonwhitespace_separator(self):
        """
        Check title parser just title with nonwhitespace separator
        """
        episode = 'Buffy-the-Vampire-Slayer'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_just_title_multiple_spaces(self):
        """
        Check title parser just title multiple spaces
        """
        episode = 'Buffy the Vampire       Slayer'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_just_title_trailing_whitespaces(self):
        """
        Check title parser just title trailing whitespaces
        """
        episode = 'Buffy the Vampire Slayer    '

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_movie_sequel_with_space(self):
        """
        Check title parser movie sequel with space
        """
        episode = 'Jaws 2'

        assert title_parser.parse_title(episode) == 'Jaws 2'

    def test_title_parser_movie_sequel_without_space(self):
        """
        Check title parser movie sequel without space
        """
        episode = 'Jaws2'

        assert title_parser.parse_title(episode) == 'Jaws2'

    def test_title_parser_episode_format_with_space(self):
        """
        Check title parser episode format with space
        """
        episode = 'Buffy the Vampire Slayer Episode 1'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_episode_format_with_title(self):
        """
        Check title parser episode format with title
        """
        episode = 'Buffy the Vampire Slayer Episode 1 - Pilot'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_duplicate_episodes(self):
        """
        Check title parser duplicate episodes
        """
        episode = 'Buffy the vampire slayer s01e03e03'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_duplicate_episodes_with_extra(self):
        """
        Check title parser duplicate episodes with extra
        """
        episode = 'Buffy the vampire slayer s01e03e03 - whatever comes after'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_year_number_combination(self):
        """
        Check title parser year number combination
        """
        episode = 'Top 100 1992'

        assert title_parser.parse_title(episode) == 'Top 100 1992'

    def test_title_parser_movie_sequel_with_year(self):
        """
        Check title parser movie sequel with year
        """
        episode = 'Jaws 2 (1976)'

        assert title_parser.parse_title(episode) == 'Jaws 2'

    def test_title_parser_movie_with_year(self):
        """
        Check title parser movie with year
        """
        episode = 'Jaws (1975)'

        assert title_parser.parse_title(episode) == 'Jaws'

    def test_title_parser_title1_suffix_lowercase(self):
        """
        Check title parser title1 suffix lowercase
        """
        episode = 'Buffy the Vampire Slayer - title1'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_title1_suffix_uppercase(self):
        """
        Check title parser title1 suffix uppercase
        """
        episode = 'Buffy the Vampire Slayer - TITLE1'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_title2_suffix_mixedcase(self):
        """
        Check title parser title2 suffix mixedcase
        """
        episode = 'Buffy the Vampire Slayer - Title2'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_title10_suffix(self):
        """
        Check title parser title10 suffix
        """
        episode = 'Buffy the Vampire Slayer.Title10'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'

    def test_title_parser_title1_suffix_underscore_separator(self):
        """
        Check title parser title1 suffix underscore separator
        """
        episode = 'Buffy_the_Vampire_Slayer_title1'

        assert title_parser.parse_title(episode) == 'Buffy The Vampire Slayer'


class TestTitleParserCustomPatterns(object):
    """
    Tests for user-defined custom patterns
    """

    def test_custom_pattern_studio_prefix(self):
        """
        Test custom pattern that handles [Studio] prefix
        """
        episode = '[Studio] My Great Show - Special Edition'
        custom_patterns = [(r'^\[Studio\][\s._-]+(.+?)[\s._-]+Special.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'My Great Show'

    def test_custom_pattern_hd_quality_marker(self):
        """
        Test custom pattern that removes HD quality markers
        """
        episode = 'Amazing Documentary - HD - 1080p'
        custom_patterns = [(r'^(.+?)[\s._-]+HD[\s._-]+\d+p.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Amazing Documentary'

    def test_custom_pattern_remaster_suffix(self):
        """
        Test custom pattern that removes REMASTER suffix
        """
        episode = 'Classic Movie_REMASTER_2023'
        custom_patterns = [(r'^(.+?)_REMASTER_\d{4}.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Classic Movie'

    def test_custom_pattern_priority_over_builtin(self):
        """
        Test that custom patterns have priority over built-in patterns
        """
        episode = '[Group] Show Title - 05'

        # Without custom pattern, this would extract "Show Title"
        # With custom pattern, we want to extract the full bracketed prefix
        custom_patterns = [(r'^\[(.+?)\][\s._-]+.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Group'

    def test_custom_pattern_fallback_to_builtin(self):
        """
        Test that built-in patterns work when custom pattern doesn't match
        """
        episode = 'Buffy the Vampire Slayer - s01e05'

        # Custom pattern won't match, should fall back to built-in
        custom_patterns = [(r'^\[STUDIO\][\s._-]+(.+?)$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Buffy The Vampire Slayer'

    def test_multiple_custom_patterns(self):
        """
        Test multiple custom patterns in order
        """
        custom_patterns = [(r'^\[STUDIO\][\s._-]+(.+?)[\s._-]+\d+.*$', 1),
                           (r'^(.+?)[\s._-]+REMASTERED[\s._-]+.*$', 1), (r'^(.+?)[\s._-]+HD[\s._-]+\d+p.*$', 1)]

        # Test first pattern
        episode1 = '[STUDIO] Show Name - 2023 - 01'
        assert title_parser.parse_title(episode1, custom_patterns) == 'Show Name'

        # Test second pattern
        episode2 = 'Old Movie - REMASTERED - Edition'
        assert title_parser.parse_title(episode2, custom_patterns) == 'Old Movie'

        # Test third pattern
        episode3 = 'Nature Documentary - HD - 720p'
        assert title_parser.parse_title(episode3, custom_patterns) == 'Nature Documentary'

    def test_custom_pattern_with_dots_as_separators(self):
        """
        Test custom pattern handles dot separators
        """
        episode = '[Release].Great.Show.Special.2023'
        custom_patterns = [(r'^\[.+?\][\s._-]+(.+?)[\s._-]+Special.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Great Show'

    def test_custom_pattern_complex_capture_group(self):
        """
        Test custom pattern with specific capture group
        """
        episode = 'PREFIX - Show Title - YEAR 2023 - SUFFIX'
        custom_patterns = [(r'^PREFIX[\s._-]+(.+?)[\s._-]+YEAR.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Show Title'

    def test_empty_custom_patterns_list(self):
        """
        Test that empty custom patterns list works (uses built-in patterns)
        """
        episode = 'Buffy the Vampire Slayer - s01e05'
        custom_patterns = []

        assert title_parser.parse_title(episode, custom_patterns) == 'Buffy The Vampire Slayer'

    def test_none_custom_patterns(self):
        """
        Test that None custom patterns works (uses built-in patterns)
        """
        episode = 'Buffy the Vampire Slayer - s01e05'

        assert title_parser.parse_title(episode, None) == 'Buffy The Vampire Slayer'

    def test_custom_pattern_preserves_title_case_conversion(self):
        """
        Test that custom patterns still apply title case conversion
        """
        episode = '[STUDIO] my great SHOW - special'
        custom_patterns = [(r'^\[STUDIO\][\s._-]+(.+?)[\s._-]+special$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'My Great Show'

    def test_custom_pattern_underscore_separator(self):
        """
        Test custom pattern with underscores as separators
        """
        episode = 'Show_Name_CUSTOM_TAG_05'
        custom_patterns = [(r'^(.+?)_CUSTOM_TAG_.*$', 1)]

        assert title_parser.parse_title(episode, custom_patterns) == 'Show Name'
