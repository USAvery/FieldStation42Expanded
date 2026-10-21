#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
TMDB (The Movie Database) API helper for fetching movie metadata
"""
import os
import json
import logging

import requests

from fs42.web.core._constants import CACHE_DIR
from fs42.web.core._constants import TMDB_BASE_URL
from fs42.core.station_manager import StationManager
from fs42.web.core._constants import TMDB_IMAGE_BASE_URL

logger = logging.getLogger('TMDB_Helper')


class TMDBHelper(object):
    """
    Helper class for fetching movie metadata from TMDB
    """

    def __init__(self, api_key=None):
        """
        Select a TMDB API key and create a reusable JSON HTTP session

        :param api_key: (str) explicit API key, or None to use global station settings
        """

        if api_key:
            self.api_key = api_key
        else:
            # Get API key from StationManager's server_conf (loaded from main_config.json)
            station_manager = StationManager()
            self.api_key = station_manager.server_conf.get('tmdb_api_key', '')

        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})

    def is_configured(self):
        """
        Check if TMDB API key is configured
        """
        return bool(self.api_key)

    def _parse_title_and_year(self, filename):
        """
        Parse filename to extract clean title and optional year

        Supports formats:
        - Movie Title (1983)
        - Movie_Title_1983
        - Movie-Title-1983
        - Movie.Title.1983

        :param filename: (obj) Raw filename without extension

        :return: Tuple of (clean_title, year) where year is None if not found
        """
        import re

        # First, try to extract year from parentheses: "Movie Title (1983)"
        year_match = re.search(r'\((\d{4})\)', filename)
        year = None
        clean_filename = filename

        if year_match:
            year = int(year_match.group(1))
            # Remove the year part from filename
            clean_filename = re.sub(r'\s*\(\d{4}\)\s*', ' ', filename)
        else:
            # Try to find 4-digit year at the end: "Movie_Title_1983"
            year_match = re.search(r'[_\-\.\s](\d{4})$', filename)
            if year_match:
                year = int(year_match.group(1))
                # Remove the year from filename
                clean_filename = re.sub(r'[_\-\.\s]\d{4}$', '', filename)

        # Normalize separators: replace underscores, dashes, dots with spaces
        clean_title = re.sub(r'[_\-\.]+', ' ', clean_filename)

        # Clean up extra whitespace
        clean_title = ' '.join(clean_title.split())

        return clean_title, year

    def _get_cache_path(self, title):
        """
        Get cache file path for a given title
        """
        # Sanitize title for filename
        safe_title = ''.join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title)
        return os.path.join(CACHE_DIR, '{}.json'.format(safe_title))

    def _load_from_cache(self, title):
        """
        Load cached TMDB data for a title
        """
        cache_path = self._get_cache_path(title)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info("Loaded TMDB data from cache for '{}'".format(title))
                    return data
            except Exception as e:
                logger.warning("Failed to load cache for '{0}': {1}".format(title, e))
        return None

    def _save_to_cache(self, title, data):
        """
        Save TMDB data to cache
        """
        cache_path = self._get_cache_path(title)
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info("Saved TMDB data to cache for '{}'".format(title))
        except Exception as e:
            logger.warning("Failed to save cache for '{0}': {1}".format(title, e))

    def search_movie(self, title):
        """
        Find the first TMDB movie match, using cached results before making an HTTP request

        :param title: (str) movie title, optionally containing a release year
        :return:      (dict) selected movie metadata, or None when unconfigured, unmatched, or unavailable
        """

        if not self.is_configured():
            logger.warning('TMDB API key not configured, skipping search')
            return None

        # Parse title to extract year if present
        clean_title, year = self._parse_title_and_year(title)

        # Check cache first (using original title as cache key)
        cached = self._load_from_cache(title)
        if cached:
            return cached

        # Search TMDB
        try:
            search_url = '{}/search/movie'.format(TMDB_BASE_URL)
            params = {'api_key': self.api_key, 'query': clean_title, 'language': 'en-US', 'page': 1}

            # Add year parameter if we found one in the filename
            if year:
                params['year'] = year
                logger.info("Searching TMDB for '{0}' ({1})".format(clean_title, year))
            else:
                logger.info("Searching TMDB for '{}'".format(clean_title))

            response = self.session.get(search_url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if not results:
                logger.info("No TMDB results found for '{}'".format(clean_title) +
                            (' ({})'.format(year) if year else ''))
                return None

            # Get the first (best) match
            movie = results[0]

            # Extract relevant data
            movie_data = {
                'tmdb_id':
                movie.get('id'),
                'title':
                movie.get('title'),
                'original_title':
                movie.get('original_title'),
                'overview':
                movie.get('overview', ''),
                'release_date':
                movie.get('release_date', ''),
                'poster_path':
                movie.get('poster_path'),
                'poster_url':
                '{0}{1}'.format(TMDB_IMAGE_BASE_URL, movie.get('poster_path'))
                if movie.get('poster_path') else None,
                'backdrop_path':
                movie.get('backdrop_path'),
                'vote_average':
                movie.get('vote_average'),
                'popularity':
                movie.get('popularity')
            }

            # Save to cache
            self._save_to_cache(title, movie_data)

            logger.info("Found TMDB match for '{0}': {1} ({2})".format(
                title, movie_data['title'],
                movie_data['release_date'][:4] if movie_data['release_date'] else 'N/A'))

            return movie_data

        except requests.exceptions.RequestException as e:
            logger.error("TMDB API request failed for '{0}': {1}".format(title, e))
            return None
        except Exception as e:
            logger.error("Unexpected error searching TMDB for '{0}': {1}".format(title, e))
            return None

    def get_movie_details(self, tmdb_id):
        """
        Request full TMDB details for a movie identifier

        :param tmdb_id: (int) TMDB movie identifier
        :return:        (dict) API movie details, or None if unconfigured or the request fails
        """

        if not self.is_configured():
            return None

        try:
            details_url = '{0}/movie/{1}'.format(TMDB_BASE_URL, tmdb_id)
            params = {'api_key': self.api_key, 'language': 'en-US'}

            response = self.session.get(details_url, params=params, timeout=5)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error('Failed to get TMDB details for ID {0}: {1}'.format(tmdb_id, e))
            return None


# Global instance
_tmdb_helper = None


def get_tmdb_helper():
    """
    Get or create global TMDB helper instance
    """
    global _tmdb_helper
    if _tmdb_helper is None:
        _tmdb_helper = TMDBHelper()
    return _tmdb_helper
