#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Exercise one real display service, idle scheduling, filesystem updates, and client-owned panel lifetimes
"""
import os
import sys
import json
import time
import subprocess
from unittest.mock import Mock

import pytest

from fs42.core.paths import PROJECT_ROOT
from fs42.tools.display.client import DisplayError
from fs42.tools.display.client import DisplayClient
from fs42.tools.media._constants import _OVERLAY_DEFAULTS


def wait_for(predicate):
    """
    Allow local socket and filesystem events to settle before asserting asynchronous state
    """
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    assert predicate()


@pytest.fixture
def service(tmp_path, monkeypatch):
    """
    Start an isolated offscreen service with short OSD durations and private runtime files
    """
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    status = tmp_path / 'status.json'
    volume = tmp_path / 'volume.json'
    config = tmp_path / 'osd.json'
    config.write_text(json.dumps([{'socket_file': str(status), 'display_time': 0.08},
                                 {'type': 'VolumeDisplay', 'socket_file': str(volume), 'display_time': 0.08}]))
    client = DisplayClient(str(tmp_path / 'service.json'), str(config)).connect()
    try:
        yield client, status, volume
    finally:
        client.close()


def test_osd_sleeps_until_status_or_volume_changes(service):
    """
    Wake on runtime-file changes, honor expiry deadlines, and stop all OSD timers while hidden
    """
    client, status, volume = service
    assert not client.request('inspect')['osd_timer_active']
    status.write_text(json.dumps({'status': 'playing', 'channel_number': 1, 'network_name': 'Station'}))
    wait_for(lambda: client.request('inspect')['osd_visible'])
    wait_for(lambda: not client.request('inspect')['osd_visible'])
    assert not client.request('inspect')['osd_timer_active']
    volume.write_text(json.dumps({'volume': '75%'}))
    wait_for(lambda: volume.exists() and volume.read_text() == '')
    wait_for(lambda: not client.request('inspect')['osd_visible'])
    assert not client.request('inspect')['osd_timer_active']
    temporary = status.with_suffix('.replacement')
    temporary.write_text(json.dumps({'status': 'playing', 'channel_number': 2, 'network_name': 'Other'}))
    def replace_status():
        """
        Retry an atomic replacement if Windows briefly observes the reader's open file handle
        """
        try:
            os.replace(temporary, status)
            return True
        except PermissionError:
            return False

    wait_for(replace_status)
    wait_for(lambda: client.request('inspect')['osd_visible'])


def test_panels_share_one_service_and_stale_handles_cannot_close_replacements(service, tmp_path):
    """
    Show concurrent panels in one process and scope closure to the exact presentation handle
    """
    client, _, _ = service
    audio = client.show('now_playing', file_path='Track.mp3', db_path=str(tmp_path / 'metadata.db'))
    prompt = client.show('parental_controls', network_name='Station')
    ticker = client.show('ticker', text='Announcement')
    assert audio.service_pid == prompt.service_pid == ticker.service_pid == client.pid
    state = client.request('inspect')
    assert set(state['panels']) == {'now_playing', 'parental_controls', 'ticker'}
    assert not state['panels']['now_playing']['timer_active']
    assert not state['panels']['parental_controls']['timer_active']
    assert state['panels']['ticker']['timer_active']
    assert state['panels']['ticker']['height'] == 100
    prompt.update(digits=2)
    prompt.update(digits=0, error=True)
    replacement = client.show('parental_controls', network_name='Replacement')
    prompt.hide()
    assert replacement.is_active()
    assert not prompt.is_active()
    assert audio.is_active()
    replacement.hide()
    ticker.hide()
    audio.hide()
    assert client.request('inspect')['panels'] == {}
    assert client.request('ping')['pid'] == client.pid


def test_ticker_rejects_overlap_and_finishes_without_stopping_service(service):
    """
    Keep one announcement at a time and retire completed tickers without quitting Qt
    """
    client, _, _ = service
    ticker = client.show('ticker', text='Announcement')
    duplicate = client.show('ticker', text='Another announcement')
    assert not duplicate.accepted
    assert ticker.is_active()
    ticker.hide()
    empty = client.show('ticker', text='')
    empty.wait(2)
    assert not empty.is_active()
    assert client.request('ping')['pid'] == client.pid


def test_disconnect_hides_only_the_departing_clients_panels(service):
    """
    Retire panels on client disconnect without stopping another client's service or panels
    """
    owner, _, _ = service
    other = DisplayClient(owner._state_file).connect(start=False)
    original = owner.show('ticker', text='Owner announcement')
    try:
        panel = other.show('parental_controls', network_name='Other client')
        assert panel.is_active()
        with pytest.raises(DisplayError, match='owning player'):
            other.request('shutdown')
    finally:
        other.close()
    wait_for(lambda: 'parental_controls' not in owner.request('inspect')['panels'])
    assert original.is_active()


def test_bad_commands_and_credentials_do_not_kill_service(service):
    """
    Reject invalid operations and credentials while preserving healthy service connections
    """
    client, _, _ = service
    with pytest.raises(DisplayError):
        client.request('unknown')
    token = client._token
    client._token = 'invalid'
    with pytest.raises(DisplayError, match='credentials'):
        client.request('ping')
    client._token = token
    assert client.request('ping')['pid'] == client.pid


def test_nfo_fades_hide_and_redisplay_without_new_processes(service):
    """
    Preserve the hidden middle section and final reappearance of timed NFO information
    """
    client, _, _ = service
    config = dict(_OVERLAY_DEFAULTS, overlay_fade_duration_ms=30)
    panel = client.show('media_info', lines=['Title', 'Information'], play_duration=0.8,
                        show_seconds=0.15, overlay_cfg=config)
    wait_for(lambda: not client.request('inspect')['panels']['media_info']['visible'])
    assert panel.is_active()
    wait_for(lambda: client.request('inspect')['panels']['media_info']['visible'])
    wait_for(lambda: not client.request('inspect')['panels']['media_info']['timer_active'])
    assert panel.service_pid == client.pid
    panel.hide()
    assert client.request('inspect')['panels'] == {}


def test_importing_display_controls_does_not_load_qt():
    """
    Keep the player-side command API free of Qt modules and GUI resource allocation
    """
    code = "from fs42.tools.overlay import run_ticker; import sys; assert 'PySide6' not in sys.modules"
    result = subprocess.run([sys.executable, '-c', code], cwd=PROJECT_ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_field_player_owns_display_startup_and_cleanup(monkeypatch):
    """
    Close the shared display connection even when playback fails during startup
    """
    from fs42.tools.field_player.field_player import FieldPlayer
    player = FieldPlayer(no_server=True)
    player._start_server = Mock()
    player._stop_server = Mock()
    player._start_display = Mock()
    player._stop_display = Mock()
    player._play_stations = Mock(side_effect=RuntimeError('Playback failed'))
    with pytest.raises(RuntimeError, match='Playback failed'):
        player.run()
    player._start_display.assert_called_once_with()
    player._stop_display.assert_called_once_with()
    player._stop_server.assert_called_once_with()


def test_owner_disconnect_stops_its_service(service):
    """
    Exit a player-started service when its owner disappears without sending a shutdown command
    """
    client, _, _ = service
    state_file = client._state_file
    client._disconnect()
    wait_for(lambda: not os.path.exists(state_file))
    client._process.wait(timeout=3)


def test_configuration_preserves_hybrid_settings_and_rejects_invalid_colors():
    """
    Normalize JSON settings while ignoring another hybrid component's fields and checking RGBA shape
    """
    from fs42.tools.osd._utils import create_config
    from fs42.tools.osd._constants import StatusDisplayConfig
    from fs42.tools.osd.osd_layout import HAlignment
    config = create_config(StatusDisplayConfig, {'halign': 'RIGHT', 'font_size': '32',
                                                'text_color': [1, 2, 3, 255], 'default_logo': 'other.png'})
    assert config.halign == HAlignment.RIGHT
    assert config.font_size == 32
    assert config.text_color == (1, 2, 3, 255)
    with pytest.raises(ValueError, match='four color channels'):
        create_config(StatusDisplayConfig, {'text_color': [1, 2]})


def test_display_failure_does_not_interrupt_pin_validation():
    """
    Keep PIN validation running when the presentation's service connection fails
    """
    from fs42.tools.field_player.station_player import StationPlayer
    player = StationPlayer.__new__(StationPlayer)
    player._l = Mock()
    player.parental_controls_panel = Mock()
    player.parental_controls_panel.update.side_effect = DisplayError('Display disconnected')
    player._update_parental_controls_overlay(digits=2)
    assert player.parental_controls_panel is None
    player._l.warning.assert_called_once()
