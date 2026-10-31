# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Persist YouTube channels and playlists and cache bounded pages of their videos."""
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit
from urllib.parse import parse_qs

from fs42.core.station_manager import StationManager

CHANNEL_ID = re.compile(r'UC[A-Za-z0-9_-]{22}')
PLAYLIST_ID = re.compile(r'(?:PL|UU|FL|OLAK5uy_)[A-Za-z0-9_-]{10,128}')
VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')
PLAYLIST_LIMIT = 100
UPLOAD_LIMIT = 30
PAGE_SIZE = 10
CACHE_SECONDS = 600
CACHE_VERSION = 2


class YouTubeError(RuntimeError):
    """Report an unavailable YouTube connection or extractor dependency."""


class YouTubeLibrary:
    """Keep subscriptions, playlists, and video metadata in the runtime database."""

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(StationManager().server_conf['db_path'], timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys = ON')
            connection.execute('CREATE TABLE IF NOT EXISTS youtube_channels '
                               '(id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS youtube_uploads '
                               '(channel_id TEXT PRIMARY KEY REFERENCES youtube_channels(id) ON DELETE CASCADE, '
                               'fetched_at REAL NOT NULL, payload TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS youtube_playlists '
                               '(id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS youtube_playlist_items '
                               '(playlist_id TEXT PRIMARY KEY REFERENCES youtube_playlists(id) ON DELETE CASCADE, '
                               'fetched_at REAL NOT NULL, payload TEXT NOT NULL)')
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def channel_url(value):
        """Accept channel IDs, handles, and YouTube channel links, never arbitrary URLs."""
        value = value.strip()
        if CHANNEL_ID.fullmatch(value):
            return 'https://www.youtube.com/channel/' + value
        if value.startswith('@'):
            value = 'https://www.youtube.com/' + value
        parsed = urlsplit(value)
        if (parsed.scheme not in ('https', 'http') or parsed.hostname not in
                ('youtube.com', 'www.youtube.com', 'm.youtube.com') or parsed.port is not None
                or parsed.username or parsed.password):
            raise ValueError('Enter a YouTube channel URL, @handle, or channel ID.')
        parts = parsed.path.strip('/').split('/')
        if parts[-1] in ('videos', 'featured', 'shorts', 'streams'):
            parts.pop()
        if not ((len(parts) == 1 and re.fullmatch(r'@[\w.-]+', parts[0])) or
                (len(parts) == 2 and parts[0] in ('channel', 'c', 'user') and
                 re.fullmatch(r'[\w.-]+', parts[1]))):
            raise ValueError('Use a channel link rather than a video or playlist link.')
        return 'https://www.youtube.com/' + '/'.join(parts)

    @staticmethod
    def playlist_url(value):
        """Normalize a public YouTube playlist ID or URL without accepting other sites."""
        value = value.strip()
        if PLAYLIST_ID.fullmatch(value):
            return 'https://www.youtube.com/playlist?list=' + value
        try:
            parsed = urlsplit(value)
            if (parsed.scheme not in ('https', 'http') or parsed.hostname not in
                    ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com')
                    or parsed.port is not None or parsed.username or parsed.password):
                raise ValueError('Enter a YouTube playlist URL or playlist ID.')
        except ValueError as error:
            raise ValueError('Enter a YouTube playlist URL or playlist ID.') from error
        if parsed.path not in ('/playlist', '/watch'):
            raise ValueError('Use a YouTube playlist link.')
        identifiers = parse_qs(parsed.query).get('list', [])
        if len(identifiers) != 1 or not PLAYLIST_ID.fullmatch(identifiers[0]):
            raise ValueError('Enter a valid YouTube playlist URL or playlist ID.')
        return 'https://www.youtube.com/playlist?list=' + identifiers[0]

    @staticmethod
    def _extract(url, limit=UPLOAD_LIMIT):
        """Read metadata without downloading videos or walking an unbounded playlist."""
        try:
            from yt_dlp import YoutubeDL
        except ImportError as error:
            raise YouTubeError('YouTube support requires yt-dlp. Install the updated requirements.') from error
        try:
            with YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': 'in_playlist',
                            'skip_download': True, 'playlistend': limit, 'socket_timeout': 15,
                            'retries': 1, 'extractor_retries': 1, 'js_runtimes': {'node': {}, 'deno': {}}}) as extractor:
                return extractor.extract_info(url, download=False)
        except Exception as error:
            raise YouTubeError('Unable to load this YouTube channel or playlist. Check the URL and connection, then retry.') from error

    def get_channels(self):
        with self._connect() as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM youtube_channels ORDER BY title COLLATE NOCASE')]

    def add_channel(self, value):
        url = self.channel_url(value)
        info = self._extract(url + '/videos', limit=1) or {}
        channel_id = info.get('channel_id') or info.get('id') or ''
        if not CHANNEL_ID.fullmatch(channel_id):
            raise ValueError('This link did not resolve to a YouTube channel.')
        channel = {'id': channel_id, 'title': info.get('channel') or info.get('uploader') or info.get('title') or channel_id,
                   'url': 'https://www.youtube.com/channel/' + channel_id}
        with self._connect() as connection:
            connection.execute('INSERT INTO youtube_channels VALUES (:id, :title, :url) '
                               'ON CONFLICT(id) DO UPDATE SET title=excluded.title, url=excluded.url', channel)
        return channel

    def remove_channel(self, channel_id):
        with self._connect() as connection:
            if not connection.execute('DELETE FROM youtube_channels WHERE id = ?', (channel_id,)).rowcount:
                raise ValueError('This YouTube channel is no longer saved.')

    def _uploads(self, channel_id):
        with self._connect() as connection:
            channel = connection.execute('SELECT * FROM youtube_channels WHERE id = ?', (channel_id,)).fetchone()
            cached = connection.execute('SELECT * FROM youtube_uploads WHERE channel_id = ?', (channel_id,)).fetchone()
        if channel is None:
            raise ValueError('This YouTube channel is no longer saved.')
        if cached and time.time() - cached['fetched_at'] < CACHE_SECONDS:
            payload = json.loads(cached['payload'])
            if isinstance(payload, dict) and payload.get('version') == CACHE_VERSION:
                return payload['items']
        # YouTube's Videos tab excludes Shorts; the combined uploads playlist includes them.
        info = self._extract(channel['url'] + '/videos') or {}
        items = []
        seen = set()
        for entry in info.get('entries') or []:
            if not entry:
                continue
            video_id = entry.get('id') or ''
            if (not VIDEO_ID.fullmatch(video_id) or video_id in seen or entry.get('live_status') in
                    ('is_live', 'is_upcoming') or entry.get('availability') in ('private', 'premium_only', 'subscriber_only')):
                continue
            seen.add(video_id)
            items.append({'id': video_id, 'source': 'youtube', 'channel_id': channel_id,
                          'title': entry.get('title') or 'Untitled upload', 'network': channel['title'],
                          'kind': 'video', 'duration': entry.get('duration') or 0,
                          'description': entry.get('description') or 'A recent upload from ' + channel['title'],
                          'year': '', 'season': None, 'episode': None})
            if len(items) == UPLOAD_LIMIT:
                break
        with self._connect() as connection:
            # Do not resurrect a channel removed while the network request was running.
            if connection.execute('SELECT 1 FROM youtube_channels WHERE id = ?', (channel_id,)).fetchone() is None:
                raise ValueError('This YouTube channel is no longer saved.')
            connection.execute('INSERT OR REPLACE INTO youtube_uploads VALUES (?, ?, ?)',
                               (channel_id, time.time(), json.dumps({'version': CACHE_VERSION, 'items': items})))
        return items

    def get_uploads(self, channel_id, page=0):
        items = self._uploads(channel_id)
        return {'items': items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], 'total': len(items),
                'page': page, 'page_size': PAGE_SIZE}

    def get_selection(self, channel_id, video_id):
        """Revalidate saved-channel membership before handing a watch URL to the player."""
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError('Invalid YouTube video.')
        for item in self._uploads(channel_id):
            if item['id'] == video_id:
                return {'file_path': 'https://www.youtube.com/watch?v=' + video_id,
                        'network_name': None, 'title': item['title'], 'source': 'youtube',
                        'source_label': 'YouTube · ' + item['network']}
        raise ValueError('This upload is no longer listed. Refresh the channel and try again.')

    def get_playlists(self):
        """
        List saved playlists in title order
        """
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM youtube_playlists ORDER BY title COLLATE NOCASE')]

    def add_playlist(self, value):
        """
        Resolve and save a playlist without downloading or enumerating its full contents
        """
        url = self.playlist_url(value)
        playlist_id = url.split('list=', 1)[1]
        info = self._extract(url, limit=1) or {}
        if info.get('id') != playlist_id:
            raise ValueError('This link did not resolve to a YouTube playlist.')
        playlist = {'id': playlist_id, 'title': info.get('title') or playlist_id, 'url': url}
        with self._connect() as connection:
            connection.execute('INSERT INTO youtube_playlists VALUES (:id, :title, :url) '
                               'ON CONFLICT(id) DO UPDATE SET title=excluded.title, url=excluded.url', playlist)
        return playlist

    def remove_playlist(self, playlist_id):
        """
        Delete a saved playlist and its cached videos
        """
        with self._connect() as connection:
            if not connection.execute('DELETE FROM youtube_playlists WHERE id = ?', (playlist_id,)).rowcount:
                raise ValueError('This YouTube playlist is no longer saved.')

    def _playlist_videos(self, playlist_id):
        """
        Read a bounded, ordered snapshot of available videos from a saved playlist
        """
        with self._connect() as connection:
            playlist = connection.execute('SELECT * FROM youtube_playlists WHERE id = ?', (playlist_id,)).fetchone()
            cached = connection.execute('SELECT * FROM youtube_playlist_items WHERE playlist_id = ?',
                                        (playlist_id,)).fetchone()
        if playlist is None:
            raise ValueError('This YouTube playlist is no longer saved.')
        if cached and time.time() - cached['fetched_at'] < CACHE_SECONDS:
            payload = json.loads(cached['payload'])
            if isinstance(payload, dict) and payload.get('version') == CACHE_VERSION:
                return payload['items']

        # Only request the first bounded set of playlist entries, preserving playlist order
        info = self._extract(playlist['url'], limit=PLAYLIST_LIMIT) or {}
        if info.get('id') != playlist_id:
            raise YouTubeError('The YouTube playlist could not be verified.')
        items = []
        seen = set()
        for entry in info.get('entries') or []:
            if not entry:
                continue
            video_id = entry.get('id') or ''
            if (not VIDEO_ID.fullmatch(video_id) or video_id in seen or entry.get('live_status') in
                    ('is_live', 'is_upcoming') or entry.get('availability') in
                    ('private', 'premium_only', 'subscriber_only')):
                continue
            seen.add(video_id)
            items.append({'id': video_id, 'source': 'youtube', 'playlist_id': playlist_id,
                          'title': entry.get('title') or 'Untitled video', 'network': playlist['title'],
                          'kind': 'video', 'duration': entry.get('duration') or 0,
                          'description': entry.get('description') or 'A video from ' + playlist['title'],
                          'year': '', 'season': None, 'episode': None})
            if len(items) == PLAYLIST_LIMIT:
                break

        with self._connect() as connection:
            if connection.execute('SELECT 1 FROM youtube_playlists WHERE id = ?',
                                  (playlist_id,)).fetchone() is None:
                raise ValueError('This YouTube playlist is no longer saved.')
            connection.execute('INSERT OR REPLACE INTO youtube_playlist_items VALUES (?, ?, ?)',
                               (playlist_id, time.time(), json.dumps({'version': CACHE_VERSION, 'items': items})))
        return items

    def get_playlist_videos(self, playlist_id, page=0):
        """
        Return one page of videos from a saved playlist
        """
        items = self._playlist_videos(playlist_id)
        return {'items': items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], 'total': len(items),
                'page': page, 'page_size': PAGE_SIZE}

    def get_playlist_selection(self, playlist_id, video_id):
        """
        Validate the video's membership in a saved playlist before returning a watch URL
        """
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError('Invalid YouTube video.')
        for item in self._playlist_videos(playlist_id):
            if item['id'] == video_id:
                return {'file_path': 'https://www.youtube.com/watch?v=' + video_id,
                        'network_name': None, 'title': item['title'], 'source': 'youtube',
                        'source_label': 'YouTube · ' + item['network']}
        raise ValueError('This video is no longer listed. Refresh the playlist and try again.')
