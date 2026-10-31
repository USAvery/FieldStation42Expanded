"""Verify saved YouTube playlists, bounded video caching, and validated playback."""
import queue
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fs42.tools.on_demand.youtube import YouTubeLibrary
from fs42.tools.on_demand.youtube import YouTubeError
from fs42.tools.field_player.station_player import StationPlayer
from fs42.tools.field_player.station_player import PlayerOutcome
from fs42.tools.field_player._constants import PlayerState
from fs42.web.app import create_app


PLAYLIST = 'PL' + 'a' * 32
VIDEO = 'abcdefghijk'


@pytest.fixture
def playlists(tmp_path, monkeypatch):
    manager = SimpleNamespace(server_conf={'db_path': str(tmp_path / 'playlists.db')})
    monkeypatch.setattr('fs42.tools.on_demand.youtube.StationManager', lambda: manager)
    monkeypatch.setattr('fs42.tools.on_demand.progress.StationManager', lambda: manager)

    def extract(url, limit=30):
        if limit == 1:
            return {'id': PLAYLIST, 'title': 'Example Playlist', '_type': 'playlist'}
        return {'id': PLAYLIST, 'entries': [
            {'id': VIDEO, 'title': 'First video', 'duration': 120},
            {'id': 'bcdefghijkl', 'title': 'Second video', 'duration': 90}
        ]}
    extractor = Mock(side_effect=extract)
    monkeypatch.setattr(YouTubeLibrary, '_extract', staticmethod(extractor))
    return YouTubeLibrary(), extractor


@pytest.mark.parametrize('value', [
    PLAYLIST,
    'https://www.youtube.com/playlist?list=' + PLAYLIST,
    'https://music.youtube.com/playlist?list=' + PLAYLIST,
    'https://www.youtube.com/watch?v=' + VIDEO + '&list=' + PLAYLIST
])
def test_playlist_inputs_normalize_and_deduplicate(playlists, value):
    library, extractor = playlists
    playlist = library.add_playlist(value)
    library.add_playlist(PLAYLIST)
    assert playlist == {'id': PLAYLIST, 'title': 'Example Playlist',
                        'url': 'https://www.youtube.com/playlist?list=' + PLAYLIST}
    assert library.get_playlists() == [playlist]
    extractor.assert_called_with(playlist['url'], limit=1)


@pytest.mark.parametrize('value', [
    'https://example.com/playlist?list=' + PLAYLIST,
    'https://youtube.com.evil.test/playlist?list=' + PLAYLIST,
    'https://youtube.com:8443/playlist?list=' + PLAYLIST,
    'https://user@youtube.com/playlist?list=' + PLAYLIST,
    'file:///playlist?list=' + PLAYLIST,
    'https://www.youtube.com/channel/' + PLAYLIST,
    'https://www.youtube.com/playlist?list=bad',
    'https://www.youtube.com/playlist?list=' + PLAYLIST + '&list=' + PLAYLIST,
    'https://www.youtube.com/watch?v=' + VIDEO,
    'https://www.youtube.com/playlist?list=UC' + 'a' * 22
])
def test_playlist_input_rejects_invalid_urls_before_network(playlists, value):
    library, extractor = playlists
    with pytest.raises(ValueError):
        library.add_playlist(value)
    extractor.assert_not_called()


def test_playlist_metadata_must_match_requested_id(playlists):
    library, extractor = playlists
    extractor.return_value = {'id': 'PL' + 'b' * 32, 'title': 'Wrong'}
    extractor.side_effect = None
    with pytest.raises(ValueError):
        library.add_playlist(PLAYLIST)
    assert library.get_playlists() == []


def test_playlist_video_order_cache_and_removal(playlists):
    library, extractor = playlists
    library.add_playlist(PLAYLIST)
    page = library.get_playlist_videos(PLAYLIST)
    assert [item['id'] for item in page['items']] == [VIDEO, 'bcdefghijkl']
    assert page['items'][0]['playlist_id'] == PLAYLIST
    assert library.get_playlist_selection(PLAYLIST, VIDEO)['file_path'] == (
        'https://www.youtube.com/watch?v=' + VIDEO)
    assert YouTubeLibrary().get_playlist_videos(PLAYLIST) == page
    assert extractor.call_count == 2
    assert library.get_playlist_videos(PLAYLIST, 1)['items'] == []
    with pytest.raises(ValueError):
        library.get_playlist_selection(PLAYLIST, 'zzzzzzzzzzz')
    library.remove_playlist(PLAYLIST)
    assert library.get_playlists() == []
    with pytest.raises(ValueError):
        library.get_playlist_selection(PLAYLIST, VIDEO)
    with library._connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM youtube_playlist_items').fetchone()[0] == 0


def test_playlist_videos_filter_invalid_live_private_duplicate_and_bound_pages(playlists):
    library, extractor = playlists
    library.add_playlist(PLAYLIST)
    extractor.side_effect = lambda url, limit=30: {'id': PLAYLIST, 'entries': [
        None, {'id': 'invalid'}, {'id': 'livevideo01', 'live_status': 'is_live'},
        {'id': 'privatevid1', 'availability': 'private'},
        *[{'id': str(index).zfill(11), 'title': str(index)} for index in range(125)],
        {'id': '00000000000', 'title': 'Duplicate'}
    ]}
    page = library.get_playlist_videos(PLAYLIST, 9)
    assert page['total'] == 100
    assert len(page['items']) == 10
    assert page['items'][0]['id'] == '00000000090'
    extractor.assert_called_with('https://www.youtube.com/playlist?list=' + PLAYLIST, limit=100)


def test_playlist_api_management_playback_and_errors(playlists):
    library, extractor = playlists
    commands = queue.Queue()
    app = create_app(server_conf={}, command_queue=commands)
    base = '/on-demand/youtube/playlists'
    with TestClient(app) as client:
        assert client.get(base).json() == {'playlists': []}
        assert client.post(base, json={'url': PLAYLIST}).status_code == 200
        assert client.get(base).json()['playlists'][0]['id'] == PLAYLIST
        assert client.get(base + '/' + PLAYLIST + '/videos?page=-1').status_code == 422
        assert client.get(base + '/' + PLAYLIST + '/videos').json()['total'] == 2
        assert client.post(base + '/' + PLAYLIST + '/play/' + VIDEO).json() == {'success': True}
        assert commands.get_nowait() == {'command': 'on_demand', 'entry_id': {
            'source': 'youtube', 'playlist_id': PLAYLIST, 'video_id': VIDEO, 'start_over': False}}
        assert client.post(base + '/' + PLAYLIST + '/play/' + VIDEO,
                           json={'start_over': True}).status_code == 200
        assert commands.get_nowait()['entry_id']['start_over'] is True
        assert client.post(base + '/' + PLAYLIST + '/play/zzzzzzzzzzz').status_code == 404
        assert commands.empty()
        assert client.delete(base + '/' + PLAYLIST).json() == {'success': True}
        assert client.get(base).json()['playlists'] == []
        assert client.post(base + '/' + PLAYLIST + '/play/' + VIDEO).status_code == 404
        extractor.side_effect = YouTubeError('Offline')
        assert client.post(base, json={'url': PLAYLIST}).status_code == 502
        assert client.post(base, json={'url': 'https://example.com/playlist'}).status_code == 400
    with TestClient(create_app(server_conf={})) as client:
        assert client.post(base + '/' + PLAYLIST + '/play/' + VIDEO).status_code == 503


def test_playlist_uses_existing_player_and_returns_to_on_demand(playlists):
    library, _ = playlists
    library.add_playlist(PLAYLIST)
    player = StationPlayer.__new__(StationPlayer)
    player._close_guide_overlay = Mock()
    player._open_guide_overlay = Mock()
    player._parental_controls_required = Mock()
    player.parental_unlocked_network = None
    player.mpv = Mock()
    player.mpv.ytdl_format = 'original-format'
    player.mpv.video_sync = 'display-resample'
    player._l = Mock()
    player.play_and_wait = Mock(return_value=PlayerOutcome(PlayerState.SUCCESS))
    with patch('fs42.tools.field_player.station_player.os.path.isfile', return_value=True):
        outcome = player.play_on_demand({'source': 'youtube', 'playlist_id': PLAYLIST, 'video_id': VIDEO})
    assert outcome.status == PlayerState.SUCCESS
    player.play_and_wait.assert_called_once_with('https://www.youtube.com/watch?v=' + VIDEO,
                                                loop=False, title='First video', is_stream=True, offset_seconds=0)
    player._open_guide_overlay.assert_called_once_with(page='on_demand')
    assert player.mpv.ytdl_format == 'original-format'
    assert player.mpv.video_sync == 'display-resample'
