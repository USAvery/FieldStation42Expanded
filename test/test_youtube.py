"""Verify saved YouTube channels, bounded upload caching, and validated playback dispatch."""
import queue
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from fs42.tools.on_demand.youtube import YouTubeLibrary, YouTubeError
from fs42.tools.on_demand._constants import YOUTUBE_FORMAT
from fs42.tools.field_player.station_player import StationPlayer, PlayerOutcome
from fs42.tools.field_player._constants import PlayerState
from fs42.web.app import create_app

CHANNEL = 'UC' + 'a' * 22
VIDEO = 'abcdefghijk'


@pytest.fixture
def youtube(tmp_path, monkeypatch):
    manager = SimpleNamespace(server_conf={'db_path': str(tmp_path / 'youtube.db')})
    monkeypatch.setattr('fs42.tools.on_demand.youtube.StationManager', lambda: manager)
    extractor = Mock(side_effect=lambda url, **kwargs:
                     {'channel_id': CHANNEL, 'channel': 'Example Channel'} if kwargs.get('limit') == 1 else
                     {'entries': [{'id': VIDEO, 'title': 'Newest upload', 'duration': 120},
                                  {'id': 'bcdefghijkl', 'title': 'Older upload', 'duration': 90}]})
    monkeypatch.setattr(YouTubeLibrary, '_extract', staticmethod(extractor))
    return YouTubeLibrary(), extractor


@pytest.mark.parametrize('value', ['@example', 'https://www.youtube.com/@example/videos',
                                   'https://youtube.com/channel/' + CHANNEL, CHANNEL])
def test_channel_inputs_resolve_and_persist_without_duplicates(youtube, value):
    service, extractor = youtube
    service.add_channel(value)
    service.add_channel('@example')
    assert YouTubeLibrary().get_channels() == [
        {'id': CHANNEL, 'title': 'Example Channel', 'url': 'https://www.youtube.com/channel/' + CHANNEL}]
    assert extractor.call_args.kwargs['limit'] == 1


@pytest.mark.parametrize('value', ['https://example.com/@example', 'https://youtube.com.evil.test/@example',
                                   'https://youtube.com/watch?v=' + VIDEO, 'file:///etc/passwd',
                                   'https://user@youtube.com/@example', 'https://youtube.com:123/@example'])
def test_non_channel_inputs_are_rejected_without_network_access(youtube, value):
    service, extractor = youtube
    with pytest.raises(ValueError):
        service.add_channel(value)
    extractor.assert_not_called()


def test_uploads_cache_across_instances_and_removal_invalidates_playback(youtube):
    service, extractor = youtube
    service.add_channel('@example')
    first = service.get_uploads(CHANNEL)
    assert [item['id'] for item in first['items']] == [VIDEO, 'bcdefghijkl']
    assert first['items'][0]['source'] == 'youtube'
    assert service.get_selection(CHANNEL, VIDEO)['file_path'] == 'https://www.youtube.com/watch?v=' + VIDEO
    assert YouTubeLibrary().get_uploads(CHANNEL) == first
    assert extractor.call_count == 2
    assert service.get_uploads(CHANNEL, page=1)['items'] == []
    with pytest.raises(ValueError):
        service.get_selection(CHANNEL, 'zzzzzzzzzzz')
    service.remove_channel(CHANNEL)
    assert YouTubeLibrary().get_channels() == []
    with pytest.raises(ValueError):
        service.get_selection(CHANNEL, VIDEO)


def test_expired_upload_cache_refreshes_and_failure_can_be_retried(youtube):
    service, extractor = youtube
    service.add_channel('@example')
    service.get_uploads(CHANNEL)
    with patch('fs42.tools.on_demand.youtube.time.time', return_value=10**12):
        extractor.side_effect = YouTubeError('Offline')
        with pytest.raises(YouTubeError):
            service.get_uploads(CHANNEL)
        extractor.side_effect = None
        extractor.return_value = {'entries': [{'id': 'zzzzzzzzzzz', 'title': 'New upload'}]}
        assert service.get_uploads(CHANNEL)['items'][0]['id'] == 'zzzzzzzzzzz'


def test_uploads_use_videos_tab_and_refresh_legacy_cache_containing_shorts(youtube):
    service, extractor = youtube
    service.add_channel('@example')
    with service._connect() as connection:
        connection.execute('INSERT INTO youtube_uploads VALUES (?, ?, ?)',
                           (CHANNEL, time.time(), json.dumps([{'id': 'shortvideo1', 'title': 'A Short'}])))
    result = service.get_uploads(CHANNEL)
    extractor.assert_called_with('https://www.youtube.com/channel/' + CHANNEL + '/videos')
    assert result['total'] == 2
    assert all(item['id'] != 'shortvideo1' for item in result['items'])
    with pytest.raises(ValueError):
        service.get_selection(CHANNEL, 'shortvideo1')
    assert YouTubeLibrary().get_uploads(CHANNEL) == result
    assert extractor.call_count == 2


def test_bounded_upload_pages_filter_private_live_invalid_and_duplicate_entries(youtube):
    service, extractor = youtube
    service.add_channel('@example')
    extractor.side_effect = None
    extractor.return_value = {'entries': [None, {'id': 'invalid'},
        {'id': 'livestream1', 'live_status': 'is_live'},
        {'id': 'privatevid1', 'availability': 'private'},
        *[{'id': str(index).zfill(11), 'title': 'Upload ' + str(index)} for index in range(40)],
        {'id': '00000000000', 'title': 'Duplicate'}]}
    page = service.get_uploads(CHANNEL, 2)
    assert page['total'] == 30
    assert len(page['items']) == 10
    assert page['items'][0]['id'] == '00000000020'


def test_youtube_api_management_playback_validation_and_offline_errors(youtube):
    service, extractor = youtube
    commands = queue.Queue()
    app = create_app(server_conf={}, command_queue=commands)
    base = '/on-demand/youtube/channels'
    with TestClient(app) as client:
        assert client.get('/youtube').status_code == 200
        assert client.post(base, json={'url': '@example'}).status_code == 200
        assert client.get(base).json()['channels'][0]['id'] == CHANNEL
        assert client.get(base + '/' + CHANNEL + '/uploads?page=-1').status_code == 422
        assert client.get(base + '/' + CHANNEL + '/uploads').json()['total'] == 2
        assert client.post(base + '/' + CHANNEL + '/play/' + VIDEO).json() == {'success': True}
        assert commands.get_nowait() == {'command': 'on_demand', 'entry_id':
            {'source': 'youtube', 'channel_id': CHANNEL, 'video_id': VIDEO}}
        assert client.post(base + '/' + CHANNEL + '/play/zzzzzzzzzzz').status_code == 404
        assert commands.empty()
        assert client.delete(base + '/' + CHANNEL).status_code == 200
        assert client.post(base + '/' + CHANNEL + '/play/' + VIDEO).status_code == 404
        assert client.get(base).json()['channels'] == []
        extractor.side_effect = YouTubeError('YouTube unavailable')
        assert client.post(base, json={'url': '@example'}).status_code == 502
        assert client.post(base, json={'url': 'https://example.com/foo'}).status_code == 400
    with TestClient(create_app(server_conf={})) as client:
        assert client.post(base + '/' + CHANNEL + '/play/' + VIDEO).status_code == 503


def test_youtube_playback_uses_existing_player_once_and_returns_to_menu(youtube):
    service, _ = youtube
    service.add_channel('@example')
    service.get_uploads(CHANNEL)
    player = StationPlayer.__new__(StationPlayer)
    player._close_guide_overlay = Mock()
    player._open_guide_overlay = Mock()
    player._parental_controls_required = Mock()
    player.parental_unlocked_network = None
    player.mpv = Mock()
    player.mpv.ytdl_format = 'original-format'
    player.mpv.video_sync = 'display-resample'
    player._l = Mock()
    def play(*args, **kwargs):
        assert player.mpv.ytdl_format == YOUTUBE_FORMAT
        assert player.mpv.video_sync == 'audio'
        return PlayerOutcome(PlayerState.SUCCESS)
    player.play_and_wait = Mock(side_effect=play)
    with patch('fs42.tools.field_player.station_player.os.path.isfile', return_value=True):
        result = player.play_on_demand({'source': 'youtube', 'channel_id': CHANNEL, 'video_id': VIDEO})
    assert result.status == PlayerState.SUCCESS
    player.play_and_wait.assert_called_once_with('https://www.youtube.com/watch?v=' + VIDEO,
                                                loop=False, title='Newest upload', is_stream=True)
    player._parental_controls_required.assert_not_called()
    player._open_guide_overlay.assert_called_once_with()
    assert player.mpv.ytdl_format == 'original-format'
    assert player.mpv.video_sync == 'display-resample'


def test_failed_youtube_playback_restores_menu_instead_of_crashing_player(youtube):
    service, _ = youtube
    service.add_channel('@example')
    player = StationPlayer.__new__(StationPlayer)
    player._close_guide_overlay = Mock()
    player._open_guide_overlay = Mock()
    player._l = Mock()
    player.mpv = Mock()
    player.mpv.ytdl_format = 'original-format'
    player.mpv.video_sync = 'display-resample'
    player.parental_unlocked_network = None
    player.play_and_wait = Mock(side_effect=RuntimeError('Video unavailable'))
    with patch('fs42.tools.field_player.station_player.os.path.isfile', return_value=True):
        result = player.play_on_demand({'source': 'youtube', 'channel_id': CHANNEL, 'video_id': VIDEO})
    assert result.status == PlayerState.FAILED
    player._open_guide_overlay.assert_called_once_with()
    assert player.mpv.ytdl_format == 'original-format'
    assert player.mpv.video_sync == 'display-resample'


def test_youtube_formats_prefer_hardware_friendly_video_over_4k_av1():
    """Reject costly codecs and high frame rates while retaining the best suitable AVC stream."""
    yt_dlp = pytest.importorskip('yt_dlp')
    formats = [
        {'format_id': 'aac', 'vcodec': 'none', 'acodec': 'mp4a.40.2', 'ext': 'm4a'},
        {'format_id': '720avc', 'vcodec': 'avc1.64001f', 'acodec': 'none', 'height': 720, 'fps': 30, 'ext': 'mp4'},
        {'format_id': '1080avc', 'vcodec': 'avc1.640028', 'acodec': 'none', 'height': 1080, 'fps': 30, 'ext': 'mp4'},
        {'format_id': '1080avc60', 'vcodec': 'avc1.64002a', 'acodec': 'none', 'height': 1080, 'fps': 60, 'ext': 'mp4'},
        {'format_id': '4kav1', 'vcodec': 'av01.0.12M.08', 'acodec': 'none', 'height': 2160, 'fps': 30, 'ext': 'mp4'},
    ]
    for item in formats:
        item['url'] = 'https://example.com/' + item['format_id']
    with yt_dlp.YoutubeDL({'quiet': True}) as extractor:
        select = extractor.build_format_selector(YOUTUBE_FORMAT)
        selected = list(select({'formats': formats, 'has_merged_format': False, 'incomplete_formats': False}))
        assert selected[0]['format_id'] == '1080avc+aac'
        selected = list(select({'formats': formats[:2], 'has_merged_format': False, 'incomplete_formats': False}))
        assert selected[0]['format_id'] == '720avc+aac'
