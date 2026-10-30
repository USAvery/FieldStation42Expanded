"""Verify durable resume positions, restart behavior, and playback checkpoints."""
from types import SimpleNamespace
import sqlite3
from unittest.mock import Mock, patch

import pytest

from fs42.tools.on_demand.progress import PlaybackHistory
from fs42.tools.on_demand._constants import MAX_RESUME_POSITIONS
from fs42.tools.on_demand.playback_controls import OnDemandPlaybackControls
from fs42.tools.field_player.station_player import StationPlayer, PlayerOutcome
from fs42.tools.field_player._constants import PlayerState


def test_progress_survives_reopening_and_is_scoped_to_the_video(tmp_path):
    path = str(tmp_path / 'history.sqlite')
    history = PlaybackHistory(path)
    key = history.media_key(str(tmp_path / 'movie.mp4'))
    assert history.position(key) == 0
    history.save(key, 123, 600)
    assert PlaybackHistory(path).position(key) == 123
    assert history.position('another-video') == 0
    assert history.media_key(str(tmp_path / '.' / 'movie.mp4')) == key
    assert history.media_key('https://www.youtube.com/watch?v=abcdefghijk', youtube=True) != key
    history.save(key, float('nan'), 600)
    assert history.position(key) == 123
    history.save(key, 599, 600)
    assert history.position(key) == 0
    history.save(key, 123, 600)
    history.save(key, 0, 600, completed=True)
    assert history.position(key) == 0


def test_resume_limit_evicts_least_recently_watched_and_refreshes_existing_entries(tmp_path):
    path = str(tmp_path / 'history.sqlite')
    history = PlaybackHistory(path)
    history.position('initialize')
    with sqlite3.connect(path) as connection:
        connection.executemany('INSERT INTO on_demand_progress VALUES (?, ?, ?, ?)',
                               [(str(i), 120, 600, i) for i in range(MAX_RESUME_POSITIONS)])
    history.save('0', 150, 600)  # Watching an old video again protects it from eviction.
    history.save('new-video', 200, 600)
    assert history.position('0') == 150
    assert history.position('new-video') == 200
    assert history.position('1') == 0
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM on_demand_progress').fetchone()[0] == MAX_RESUME_POSITIONS


def test_old_progress_schema_is_migrated_and_trimmed_without_losing_recent_entries(tmp_path):
    path = str(tmp_path / 'history.sqlite')
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE on_demand_progress (media_key TEXT PRIMARY KEY, position REAL, duration REAL)')
        connection.executemany('INSERT INTO on_demand_progress VALUES (?, ?, ?)',
                               [(str(i), 120, 600) for i in range(MAX_RESUME_POSITIONS + 3)])
    history = PlaybackHistory(path)
    assert history.position(str(MAX_RESUME_POSITIONS + 2)) == 120
    assert history.position('0') == 0
    history.save('new-video', 130, 600)
    assert PlaybackHistory(path).position('new-video') == 130
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM on_demand_progress').fetchone()[0] == MAX_RESUME_POSITIONS


def test_hidden_controls_checkpoint_progress_and_finish_saves_the_final_position(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('fs42.tools.on_demand.playback_controls.time.monotonic', lambda: clock[0])
    history = PlaybackHistory(str(tmp_path / 'history.sqlite'))
    mpv = SimpleNamespace(time_pos=120, duration=600, pause=False, paused_for_cache=False)
    controller = OnDemandPlaybackControls(mpv, Mock(), 'Movie', 'Network', history, 'movie')
    controller.start()
    assert history.position('movie') == 120
    controller.hide()
    mpv.time_pos = 126
    clock[0] += 6
    controller.tick()
    assert history.position('movie') == 126
    mpv.time_pos = 129
    controller.stop()
    assert history.position('movie') == 129
    # A failed load never erases a previous resume point, even for a restart request.
    failed = OnDemandPlaybackControls(mpv, Mock(), 'Movie', 'Network', history, 'movie')
    failed.stop(completed=True)
    assert history.position('movie') == 129
    controller.start()
    mpv.time_pos = None  # MPV can drop timestamps at EOF.
    controller.stop(completed=True)
    assert history.position('movie') == 0


@pytest.mark.parametrize('youtube', [False, True])
@pytest.mark.parametrize('start_over', [False, True])
def test_selection_resumes_or_restarts_in_the_existing_player(tmp_path, youtube, start_over):
    history = PlaybackHistory(str(tmp_path / 'history.sqlite'))
    path = 'https://www.youtube.com/watch?v=abcdefghijk' if youtube else str(tmp_path / 'movie.mp4')
    key = history.media_key(path, youtube)
    history.save(key, 87, 600)
    player = StationPlayer.__new__(StationPlayer)
    player._close_guide_overlay = Mock()
    player._open_guide_overlay = Mock()
    player._parental_controls_required = Mock(return_value=False)
    player._l = Mock()
    player.mpv = Mock()
    player.parental_unlocked_network = None
    player.play_and_wait = Mock(return_value=PlayerOutcome(PlayerState.SUCCESS))
    selection = {'file_path': path, 'network_name': None, 'title': 'A video'}
    request = {'source': 'youtube', 'channel_id': 'channel', 'video_id': 'abcdefghijk', 'start_over': start_over} if youtube else {
        'source': 'catalog', 'entry_id': 12, 'start_over': start_over}
    with patch('fs42.tools.field_player.station_player.PlaybackHistory', return_value=history), \
            patch('fs42.tools.on_demand.OnDemand') as catalog, \
            patch('fs42.tools.on_demand.youtube.YouTubeLibrary') as library, \
            patch('fs42.tools.field_player.station_player.os.path.isfile', return_value=True):
        catalog.return_value.get_selection.return_value = selection
        library.return_value.get_selection.return_value = selection
        assert player.play_on_demand(request).status == PlayerState.SUCCESS
    args = {'loop': False, 'title': 'A video', 'offset_seconds': 0 if start_over else 87}
    if youtube:
        args['is_stream'] = True
    player.play_and_wait.assert_called_once_with(path, **args)
    # The mocked playback never becomes ready: merely selecting an option must not clear history.
    assert history.position(key) == 87
