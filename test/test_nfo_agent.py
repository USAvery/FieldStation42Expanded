#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify XML and plain-text NFO parsing, display-field extraction, and eligibility rules for metadata
overlays.
"""
import pytest

from fs42.tools.media import nfo_agent


class TestParseNfoString(object):
    """
    Verify XML and plaintext NFO content becomes structured media metadata
    """

    def test_musicvideo(self):
        """
        Check musicvideo
        """
        content = """<?xml version='1.0' encoding='utf-8'?>
        <musicvideo>
          <title>No Rain</title>
          <artist>Blind Melon</artist>
          <album>Live at the Palace</album>
          <year>1993</year>
          <genre>Alternative Rock</genre>
        </musicvideo>"""
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {
            'type': 'music',
            'title': 'No Rain',
            'artist': 'Blind Melon',
            'album': 'Live at the Palace',
            'year': '1993',
            'genre': 'Alternative Rock',
        }

    def test_musicvideo_year_falls_back_to_premiered(self):
        """
        Check musicvideo year falls back to premiered
        """
        content = """<musicvideo>
          <title>Song</title>
          <artist>Someone</artist>
          <premiered>1988-05-01</premiered>
        </musicvideo>"""
        meta = nfo_agent.parse_nfo_string(content)
        assert meta['year'] == '1988'

    def test_movie(self):
        """
        Check movie
        """
        content = """<movie>
          <title>The Thing</title>
          <year>1982</year>
          <plot>A shape-shifting alien.</plot>
          <genre>Horror</genre>
        </movie>"""
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {
            'type': 'movie',
            'title': 'The Thing',
            'year': '1982',
            'plot': 'A shape-shifting alien.',
            'genre': 'Horror',
        }

    def test_movie_plot_falls_back_to_outline(self):
        """
        Check movie plot falls back to outline
        """
        content = '<movie><title>X</title><outline>short</outline></movie>'
        meta = nfo_agent.parse_nfo_string(content)
        assert meta['plot'] == 'short'

    def test_episodedetails_converts_season_episode_to_int(self):
        """
        Check episodedetails converts season episode to int
        """
        content = """<episodedetails>
          <title>The Constant</title>
          <showtitle>Lost</showtitle>
          <season>4</season>
          <episode>5</episode>
          <aired>2008-02-28</aired>
          <plot>Desmond.</plot>
        </episodedetails>"""
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {
            'type': 'episode',
            'title': 'The Constant',
            'show_title': 'Lost',
            'season': 4,
            'episode': 5,
            'aired': '2008-02-28',
            'plot': 'Desmond.',
        }

    def test_tvshow(self):
        """
        Check tvshow
        """
        content = '<tvshow><title>Lost</title><year>2004</year></tvshow>'
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {'type': 'tvshow', 'title': 'Lost', 'year': '2004'}

    def test_unknown_tag_generic_fallback(self):
        """
        Check unknown tag generic fallback
        """
        content = '<artist><title>Blind Melon</title><genre>Rock</genre></artist>'
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {'type': 'artist', 'title': 'Blind Melon', 'genre': 'Rock'}

    def test_unknown_tag_without_title_is_none(self):
        """
        Check unknown tag without title is none
        """
        content = '<artist><formed>1990</formed></artist>'
        assert nfo_agent.parse_nfo_string(content) is None

    def test_empty_fields_are_dropped(self):
        """
        Check empty fields are dropped
        """
        content = '<movie><title>X</title><year></year><plot></plot></movie>'
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {'type': 'movie', 'title': 'X'}

    def test_plain_text_fallback(self):
        """
        Check plain text fallback
        """
        content = "Blind Melon\nNo Rain\nLive at the Palace\n1993\n"
        meta = nfo_agent.parse_nfo_string(content)
        assert meta == {
            'type': 'plaintext',
            'title': 'Blind Melon',
            'lines': ['Blind Melon', 'No Rain', 'Live at the Palace', '1993'],
        }

    def test_plain_text_caps_at_max_lines(self):
        """
        Check plain text caps at max lines
        """
        content = "\n".join(str(i) for i in range(10))
        meta = nfo_agent.parse_nfo_string(content)
        assert len(meta['lines']) == 5

    def test_empty_content_is_none(self):
        """
        Check empty content is none
        """
        assert nfo_agent.parse_nfo_string("   \n  \n") is None


class TestOverlayLines(object):
    """
    Verify supported metadata types produce bounded, nonempty overlay lines
    """

    def test_music_order_is_artist_title_album_year(self):
        """
        Check music order is artist title album year
        """
        meta = {
            'type': 'music',
            'title': 'No Rain',
            'artist': 'Blind Melon',
            'album': 'Live at the Palace',
            'year': '1993',
        }
        assert nfo_agent.overlay_lines(meta) == [
            'Blind Melon',
            'No Rain',
            'Live at the Palace',
            '1993',
        ]

    def test_music_skips_missing_fields(self):
        """
        Check music skips missing fields
        """
        meta = {'type': 'music', 'title': 'Solo', 'artist': 'Nobody'}
        assert nfo_agent.overlay_lines(meta) == ['Nobody', 'Solo']

    def test_plaintext_returns_lines(self):
        """
        Check plaintext returns lines
        """
        meta = {'type': 'plaintext', 'lines': ['a', 'b', 'c']}
        assert nfo_agent.overlay_lines(meta) == ['a', 'b', 'c']

    def test_movie_is_not_overlay_eligible(self):
        """
        Check movie is not overlay eligible
        """
        meta = {'type': 'movie', 'title': 'The Thing', 'year': '1982'}
        assert nfo_agent.overlay_lines(meta) is None

    def test_episode_is_not_overlay_eligible(self):
        """
        Check episode is not overlay eligible
        """
        meta = {'type': 'episode', 'title': 'The Constant'}
        assert nfo_agent.overlay_lines(meta) is None

    def test_none_is_none(self):
        """
        Check none is none
        """
        assert nfo_agent.overlay_lines(None) is None


class TestDisplayFields(object):
    """
    Verify media metadata maps into common title, information, and description fields
    """

    def test_music(self):
        """
        Check music
        """
        meta = {'type': 'music', 'title': 'No Rain', 'artist': 'Blind Melon', 'album': 'LATP'}
        assert nfo_agent.display_fields(meta) == {
            'title': 'No Rain',
            'info': 'Blind Melon',
            'description': 'LATP',
        }

    def test_movie(self):
        """
        Check movie
        """
        meta = {'type': 'movie', 'title': 'The Thing', 'year': '1982', 'plot': 'Alien.'}
        assert nfo_agent.display_fields(meta) == {
            'title': 'The Thing',
            'info': '1982',
            'description': 'Alien.',
        }

    def test_episode(self):
        """
        Check episode
        """
        meta = {'type': 'episode', 'title': 'The Constant', 'show_title': 'Lost', 'plot': 'D.'}
        assert nfo_agent.display_fields(meta) == {
            'title': 'The Constant',
            'info': 'Lost',
            'description': 'D.',
        }

    def test_plaintext(self):
        """
        Check plaintext
        """
        meta = {'type': 'plaintext', 'lines': ['a', 'b', 'c', 'd']}
        assert nfo_agent.display_fields(meta) == {
            'title': 'a',
            'info': 'b',
            'description': 'c',
        }

    def test_none_is_none(self):
        """
        Check none is none
        """
        assert nfo_agent.display_fields(None) is None
