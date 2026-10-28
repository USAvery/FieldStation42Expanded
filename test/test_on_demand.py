#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify catalog filtering, validated playback requests, parental authorization, and single-play completion
"""
import os
import json
import queue
import sqlite3
import importlib
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fs42.web.app import create_app
from fs42.web.remote_app import create_app as create_remote_app
from fs42.tools.on_demand import OnDemand
from fs42.tools.catalog.catalog_io import CatalogIO
from fs42.tools.field_player._constants import PlayerState
from fs42.tools.field_player.station_player import PlayerOutcome
from fs42.tools.field_player.station_player import StationPlayer
from fs42.tools.field_player.field_player import FieldPlayer
from fs42.tools.field_player.station_player import update_status_socket
from fs42.tools.web_channel.web_render import WebRenderApp


@pytest.fixture
def library(tmp_path, monkeypatch):
    """
    Build a real catalog containing duplicate features, episodes, fillers, and unavailable stations
    """
    database = str(tmp_path / 'catalog.db')
    stations = [{'network_name': 'Movies', '_has_catalog': True},
                {'network_name': 'Kids', '_has_catalog': True}]
    manager = SimpleNamespace(stations=stations, server_conf={'db_path': database})
    monkeypatch.setattr('fs42.tools.catalog.catalog_io.StationManager', lambda: manager)
    monkeypatch.setattr('fs42.tools.on_demand.on_demand.StationManager', lambda: manager)
    CatalogIO()
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE file_meta (path TEXT PRIMARY KEY, meta TEXT)')
        for index in range(15):
            path = str(tmp_path / ('Show.S01E01.mp4' if index == 1 else 'Movie{}.mp4'.format(index)))
            with open(path, 'w') as f_out:
                f_out.write('test video')
            station = 'Kids' if index == 1 else 'Movies'
            content_type = 'commercial' if index == 13 else 'feature'
            media_type = 'audio' if index == 14 else 'video'
            connection.execute('''INSERT INTO catalog_entries
                (station, path, realpath, title, duration, tag, content_type, media_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (station, path, path, 'Title {}'.format(index), 3600, 'family' if index == 1 else 'movies',
                 content_type, media_type))
            meta = {'type': 'episode', 'title': 'First Episode', 'show_title': 'Example Show', 'season': 1,
                    'episode': 1} if index == 1 else {'type': 'movie', 'title': 'Movie {}'.format(index)}
            connection.execute('INSERT INTO file_meta VALUES (?, ?)', (path, json.dumps(meta)))
        connection.execute('''INSERT INTO catalog_entries
            (station, path, realpath, title, duration, tag, content_type, media_type)
            SELECT 'Kids', path, realpath, title, duration, 'duplicate', content_type, media_type
            FROM catalog_entries WHERE id = 1''')
        connection.execute('''INSERT INTO catalog_entries
            (station, path, title, duration, tag) VALUES ('Inactive', 'secret.mp4', 'Hidden', 3600, 'hidden')''')
    return OnDemand(), database, manager


def test_library_pages_exclude_fillers_and_inactive_stations_and_deduplicate_files(library):
    """
    Bound each result page and include each active local feature only once
    """
    service, _, _ = library
    first = service.get_titles()
    second = service.get_titles(page=1)
    assert first['total'] == 13
    assert len(first['items']) == 10
    assert len(second['items']) == 3
    assert not ({item['id'] for item in first['items']} & {item['id'] for item in second['items']})
    assert 'file_path' not in first['items'][0]


def test_episode_metadata_categories_and_literal_search(library):
    """
    Classify cached episodes and search series names without treating SQL wildcards as patterns
    """
    service, _, _ = library
    episode = service.get_titles(category='tv')['items'][0]
    assert episode['title'] == 'Example Show: First Episode'
    assert episode['season'] == episode['episode'] == 1
    assert service.get_titles(category='movies')['total'] == 12
    assert service.get_titles(category='kids')['total'] == 1
    assert service.get_titles(query='Example Show')['total'] == 1
    assert service.get_titles(query="%' OR 1=1 --")['total'] == 0
    assert service.get_titles(channel='Not a channel')['total'] == 0
    assert service.get_titles(channel='Kids')['total'] == 2


def test_player_recognizes_the_single_title_command_without_changing_channels():
    """
    Translate the API's catalog selection into the dedicated single-play state
    """
    player = FieldPlayer(no_server=True)
    player._command_queue = queue.Queue()
    player._command_queue.put({'command': 'on_demand', 'entry_id': 42})
    outcome = player._check_input()
    assert outcome.status == PlayerState.ON_DEMAND
    assert outcome.payload == 42


def test_dedicated_remote_opens_menu_without_starting_playback(library):
    """
    Route the dedicated button directly to a non-interrupting menu command
    """
    commands = queue.Queue()
    with TestClient(create_app(command_queue=commands, server_conf={})) as client:
        assert client.post('/on-demand/open').json() == {'success': True}
        assert 'data-key="on_demand"' in client.get('/static/remote.html').text
        assert 'guide-on-demand' not in client.get('/static/customguide/customguide.html').text
    player = FieldPlayer(no_server=True)
    player._command_queue = commands
    outcome = player._check_input()
    assert outcome.status == PlayerState.SUCCESS
    assert outcome.payload == 'on_demand_menu'
    playback = StationPlayer.__new__(StationPlayer)
    playback._open_guide_overlay = Mock()
    assert playback.handle_runtime_command_outcome(outcome)
    playback._open_guide_overlay.assert_called_once_with(page='on_demand')
    with TestClient(create_app(server_conf={})) as client:
        assert client.post('/on-demand/open').status_code == 503


def test_menu_command_navigates_the_existing_renderer_on_the_same_server():
    """
    Reuse the existing Qt window and preserve its server address when opening On Demand
    """
    commands = queue.Queue()
    commands.put({'type': 'show_window', 'page': 'on_demand'})
    window = SimpleNamespace(current_url='http://localhost:4242/static/customguide/customguide.html',
                             navigate=Mock())
    renderer = SimpleNamespace(queue=commands, window=window, show_window=Mock(),
                               _handle_presentation_message=Mock(return_value=False))
    WebRenderApp.tick(renderer)
    window.navigate.assert_called_once_with('http://localhost:4242/on-demand')
    renderer.show_window.assert_called_once_with()


def test_standalone_remote_button_uses_the_existing_file_command_transport(tmp_path):
    """
    Open On Demand through the standalone remote without needing the main server's command queue
    """
    with TestClient(create_remote_app()) as client:
        assert 'openOnDemand()' in client.get('/').text
        with patch('fs42.tools.field_player.remote_commands.write_command', return_value={}) as write:
            assert client.post('/api/command', json={'command': 'on_demand_menu', 'channel': -1}).status_code == 200
            write.assert_called_once_with({'command': 'on_demand_menu', 'channel': -1})
    path = str(tmp_path / 'channel.socket')
    with open(path, 'w') as f_out:
        json.dump({'command': 'on_demand_menu', 'channel': -1}, f_out)
    player = FieldPlayer(no_server=True)
    with patch('fs42.tools.field_player.field_player.StationManager') as manager:
        manager.return_value.server_conf = {'channel_socket': path}
        outcome = player._check_input()
    assert outcome.status == PlayerState.SUCCESS
    assert outcome.payload == 'on_demand_menu'


def test_catalog_without_metadata_table_still_recognizes_episode_filenames(library):
    """
    Keep older catalogs browsable before cached NFO metadata has been populated
    """
    service, database, _ = library
    with sqlite3.connect(database) as connection:
        connection.execute('DROP TABLE file_meta')
    assert service.get_titles(category='tv')['total'] == 1


def test_selection_rejects_missing_files_and_non_feature_or_inactive_entries(library):
    """
    Resolve playback by catalog ID and recheck local availability rather than accepting arbitrary paths
    """
    service, _, _ = library
    selection = service.get_selection(1)
    assert selection['network_name'] == 'Movies'
    for entry_id in (14, 15, 17, 999):
        with pytest.raises(ValueError):
            service.get_selection(entry_id)
    os.remove(selection['file_path'])
    with pytest.raises(ValueError):
        service.get_selection(1)


def test_menu_api_queues_only_valid_catalog_ids_and_reports_disconnected_player(library):
    """
    Validate request boundaries and queue a single-play command only for an available title
    """
    commands = queue.Queue()
    with TestClient(create_app(command_queue=commands, server_conf={})) as client:
        assert client.get('/on-demand/menu').status_code == 200
        assert client.get('/on-demand/titles?page=-1').status_code == 422
        assert client.get('/on-demand/titles?category=unknown').status_code == 400
        assert client.get('/on-demand/titles?query=' + 'a' * 201).status_code == 422
        assert client.post('/on-demand/play/14').status_code == 404
        assert commands.empty()
        assert client.post('/on-demand/play/1').json() == {'success': True}
        assert commands.get_nowait() == {'command': 'on_demand', 'entry_id': 1}
    with TestClient(create_app(server_conf={})) as client:
        assert client.post('/on-demand/play/1').status_code == 503


def test_on_demand_page_and_assets_resolve_without_external_media(library):
    """
    Serve both entry URLs and use the existing Comcast logo without browser audio or video players
    """
    with TestClient(create_app(server_conf={})) as client:
        for url in ('/on-demand', '/static/on_demand/on_demand.html'):
            response = client.get(url)
            assert response.status_code == 200
            assert 'comcast_logo.png' in response.text
            assert '<video' not in response.text and '<audio' not in response.text
        for name in ('on_demand.js', 'on_demand.css'):
            assert client.get('/static/tools/on_demand/' + name).status_code == 200


@pytest.mark.parametrize('endpoint,action,command', [
    ('play-pause', 'play_pause', ('cycle', 'pause')),
    ('rewind', 'rewind', ('seek', -10, 'relative+exact')),
    ('fast-forward', 'fast_forward', ('seek', 10, 'relative+exact')),
])
def test_remote_transport_controls_queue_non_interrupting_mpv_actions(endpoint, action, command):
    """Playback controls act on the current player instead of opening media or changing channel."""
    commands = queue.Queue()
    with TestClient(create_app(command_queue=commands, server_conf={})) as client:
        response = client.post('/player/mpv/' + endpoint)
        assert response.status_code == 200
        assert commands.get_nowait() == {'command': 'mpv_command', 'action': action}
        assert commands.empty()
    player = StationPlayer.__new__(StationPlayer)
    player.mpv = Mock()
    player._l = Mock()
    outcome = PlayerOutcome(PlayerState.SUCCESS, 'mpv_command:' + action)
    assert player.handle_runtime_command_outcome(outcome)
    player.mpv.command.assert_called_once_with(*command)
    player.mpv.play.assert_not_called()
    player.mpv.terminate.assert_not_called()
    with TestClient(create_app(server_conf={})) as client:
        assert client.post('/player/mpv/' + endpoint).status_code == 503


def test_single_play_finishes_at_eof_without_replacing_or_looping_mpv():
    """
    End an On Demand title at EOF while keeping the same MPV client available for the next channel
    """
    player = StationPlayer.__new__(StationPlayer)
    player.mpv = Mock(eof_reached=True)
    player.play_file = Mock(return_value=True)
    player._close_now_playing = Mock()
    player._poll_metadata_overlay = Mock()
    player._drain_guide_events = Mock()
    player._check_audio_clock = Mock()
    assert player.play_and_wait('movie.mp4', loop=False).status == PlayerState.SUCCESS
    assert player.mpv.loop_playlist == 'no'
    player.mpv.terminate.assert_not_called()


def test_menu_visibility_preserves_station_status_and_resets_after_shutdown(tmp_path):
    """
    Publish overlay visibility independently of the tuned station so remote routing follows open menus
    """
    path = str(tmp_path / 'status.json')
    manager = SimpleNamespace(server_conf={'status_socket': path})
    player = StationPlayer.__new__(StationPlayer)
    player._l = Mock()
    player.guide_visible = True
    with patch('fs42.tools.field_player.station_player.StationManager', return_value=manager):
        update_status_socket('playing', 'Discovery', 21)
        player._publish_guide_visibility()
        update_status_socket('playing', 'Discovery', 21, title='Next program')
        with open(path) as f_in:
            status = json.load(f_in)
        assert status['guide_visible']
        assert status['channel_number'] == 21
        update_status_socket('stopped', '', -1)
        with open(path) as f_in:
            assert not json.load(f_in)['guide_visible']


def test_remote_routes_visible_menus_over_a_normal_channel(monkeypatch):
    """
    Send real directional arrows to overlays even when playback status still names the live channel
    """
    import sys
    monkeypatch.setitem(sys.modules, 'evdev', SimpleNamespace(ecodes=Mock(), InputDevice=Mock()))
    remote = importlib.import_module('fs42.tools.remote_control.remote_control')
    response = Mock(ok=True)
    response.json.return_value = {'channel_number': 21, 'guide_visible': True}
    with patch.object(remote, 'get_custom_guide_channel', return_value=4), \
            patch.object(remote.requests, 'get', return_value=response), \
            patch.object(remote, 'send_custom_guide_key') as send:
        assert remote.custom_guide_is_active()
        assert remote.handle_key_name('up')
        send.assert_called_once_with('ArrowUp')


@pytest.mark.parametrize('authorized', [True, False])
def test_on_demand_respects_pin_interruptions_and_returns_to_menu_after_completion(authorized):
    """
    Require the source station's parental authorization before playback and retain normal channel interruptions
    """
    player = StationPlayer.__new__(StationPlayer)
    player._close_guide_overlay = Mock()
    player._open_guide_overlay = Mock()
    player._parental_controls_required = Mock(return_value=True)
    player.mpv = Mock()
    player.parental_unlocked_network = None
    outcome = PlayerState.SUCCESS if authorized else PlayerState.CHANNEL_CHANGE
    player.prompt_parental_controls = Mock(return_value=PlayerOutcome(outcome))
    player.play_and_wait = Mock(return_value=PlayerOutcome(PlayerState.SUCCESS))
    with patch('fs42.tools.on_demand.OnDemand') as service, \
            patch('fs42.tools.field_player.station_player.StationManager'):
        service.return_value.get_selection.return_value = {'file_path': 'movie.mp4', 'network_name': 'Locked',
                                                            'title': 'Movie'}
        assert player.play_on_demand(1).status == outcome
    if authorized:
        player.play_and_wait.assert_called_once_with('movie.mp4', loop=False, title='Movie')
        player._open_guide_overlay.assert_called_once_with()
    else:
        player.play_and_wait.assert_not_called()
        player._open_guide_overlay.assert_not_called()
