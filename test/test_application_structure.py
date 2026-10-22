#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Check application factories, page and asset routes, CLI launchers, shutdown behavior, and
compatibility with saved catalog hints.
"""
import os
import re
import sys
import json
import queue
import asyncio
import subprocess
from unittest.mock import Mock
from unittest.mock import patch
from urllib.parse import urljoin
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from fs42.web.app import create_app
from fs42.web.core import _constants
from fs42.tools.station import _utils
from fs42.web.app import _monitor_shutdown
from fs42.tools.catalog import catalog_entry
from fs42.tools.schedule import schedule_hint
from fs42.tools.station.station import Station

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = [
    '/', '/remote', '/static/about.html', '/static/catalog.html', '/static/diagnostics.html', '/static/guide.html',
    '/static/guide_frame.html', '/static/index.html', '/static/remote.html', '/static/schedule.html',
    '/static/stations.html', '/static/station_editor.html', '/static/bump/bump.html',
    '/static/customguide/customguide.html', '/static/ppv/ppv.html'
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    Build an isolated web application without loading local station data
    """
    monkeypatch.setattr(_constants, 'GUIDE_VIDEO_DIR', str(tmp_path / 'guide_videos'))
    return TestClient(create_app(server_conf={}))


@pytest.mark.parametrize('url', PAGES)
def test_pages_render_and_local_assets_resolve(client, url):
    """
    Keep the existing page URLs and their script and stylesheet links working
    """
    response = client.get(url)
    assert response.status_code == 200
    assert '<html' in response.text
    assert '{% ' not in response.text
    for asset in re.findall(r'(?:src|href)="([^"]+)"', response.text):
        if asset.startswith(('http:', 'https:', '#', 'data:')):
            continue
        if not asset.split('?')[0].endswith(('.js', '.css', '.ico')):
            continue
        asset_url = urljoin(url, asset)
        result = client.get(asset_url)
        assert result.status_code == 200, asset_url


def test_public_script_urls_still_resolve(client):
    """
    Preserve shared script URLs used by custom pages
    """
    assert client.get('/static/common.js').status_code == 200
    assert client.get('/static/fs42_client.js').status_code == 200


def test_factory_owns_player_and_job_state(tmp_path, monkeypatch):
    """
    Keep command queues and background job results isolated between applications
    """
    monkeypatch.setattr(_constants, 'GUIDE_VIDEO_DIR', str(tmp_path / 'guide_videos'))
    command_queue = queue.Queue()
    first = create_app(command_queue=command_queue, server_conf={})
    second = create_app(server_conf={})
    first.state.web.rebuild_tasks['test'] = {'status': 'done', 'log': 'Completed'}
    assert first.state.player_command_queue is command_queue
    assert second.state.player_command_queue is None
    assert second.state.web.rebuild_tasks == {}
    with TestClient(first) as first_client, TestClient(second) as second_client:
        assert first_client.get('/player/status/queue_connected').json()['queue_connected'] is True
        assert second_client.get('/player/status/queue_connected').json()['queue_connected'] is False
        assert first_client.get('/build/catalog/status/test').json()['status'] == 'done'
        assert second_client.get('/build/catalog/status/test').json() == {'error': 'Task ID not found.'}


def test_api_keeps_request_validation(client):
    """
    Keep body and path validation after reorganizing endpoint modules
    """
    schema = client.get('/openapi.json').json()
    assert '/stations' in schema['paths']
    assert '/player/info' in schema['paths']
    assert '/build/catalog/{network_name}' in schema['paths']
    assert 'station_conf' in schema['components']['schemas']['StationConfigRequest']['required']
    assert client.post('/stations', json={}).status_code == 422


def test_shutdown_monitor_requests_graceful_exit():
    """
    Stop the server through its lifecycle rather than terminating the process
    """
    shutdown_queue = queue.Queue()
    shutdown_queue.put('shutdown')
    server = SimpleNamespace(should_exit=False)
    app = SimpleNamespace(state=SimpleNamespace(shutdown_queue=shutdown_queue, server=server))
    with patch('fs42.web.app.asyncio.sleep', return_value=None):
        asyncio.run(_monitor_shutdown(app))
    assert server.should_exit is True


@pytest.mark.parametrize('script', ['station_42.py', 'field_player.py', 'bin/station42', 'bin/fieldPlayer'])
def test_command_help_from_another_directory(script, tmp_path):
    """
    Keep both legacy and bin launchers importable outside the repository directory
    """
    result = subprocess.run([sys.executable, os.path.join(ROOT, script), '--help'], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout


def test_station_rebuild_preserves_scan_options():
    """
    Pass force and chapter-scan options through the administration tool
    """
    args = _utils.build_parser().parse_args(['--force', '--skip_chapter_scan'])
    config = {'network_name': 'Example'}
    with patch('fs42.tools.station.station.ShowCatalog') as catalog:
        Station(args)._rebuild_catalog(config)
    catalog.assert_called_once_with(config, rebuild_catalog=True, force=True, skip_chapter_scan=True)


def test_player_releases_server_when_playback_fails():
    """
    Release the player's child process when playback exits through an exception
    """
    from fs42.tools.field_player.field_player import FieldPlayer
    player = FieldPlayer(no_server=True)
    player._start_display = Mock()
    player._stop_display = Mock()
    player._start_server = Mock()
    player._stop_server = Mock()
    player._play_stations = Mock(side_effect=RuntimeError('playback failed'))
    with pytest.raises(RuntimeError, match='playback failed'):
        player.run()
    player._stop_server.assert_called_once()


def test_catalog_restores_saved_hint_data():
    """
    Restore scheduling hints from the existing database representation
    """
    original = schedule_hint.MonthHint('October')
    hints = json.dumps([json.dumps(original.to_json())])
    row = (1, 'Example', 'show.mp4', 'Show', 120.0, 'content', 0, hints, None, None, None, 'feature', 'video')
    entry = catalog_entry.from_db_row(row)
    assert len(entry.hints) == 1
    assert isinstance(entry.hints[0], schedule_hint.MonthHint)
    assert entry.hints[0].to_json() == original.to_json()


def test_bump_video_resolves_from_page_assets(tmp_path, monkeypatch):
    """
    Find a configured background video after the web assets move
    """
    from fs42.tools.catalog import autobump_agent
    from fs42.tools.catalog import _constants as catalog_constants
    monkeypatch.chdir(tmp_path)
    directory = os.path.join(str(tmp_path), catalog_constants.BUMP_VIDEO_DIR)
    os.makedirs(directory)
    video_path = os.path.join(directory, 'background.mp4')
    with open(video_path, 'wb') as f_out:
        f_out.write(b'video fixture')
    resolved = autobump_agent.resolve_bg_video_path('background.mp4')
    assert os.path.abspath(resolved) == video_path
    assert autobump_agent.resolve_bg_video_url('background.mp4').endswith('/static/bump/video/background.mp4')
    assert autobump_agent.resolve_bg_video_path('missing.mp4') is None
