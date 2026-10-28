"""Check transport timing, session-safe timeline seeks, and native-browser presentation."""
import json
import queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from fs42.tools.on_demand.playback_controls import OnDemandPlaybackControls
from fs42.tools.field_player.field_player import FieldPlayer
from fs42.tools.field_player.station_player import StationPlayer, PlayerOutcome
from fs42.tools.field_player._constants import PlayerState
from fs42.tools.web_channel.web_render import WebRenderApp
from fs42.web.app import create_app


@pytest.fixture
def controls(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('fs42.tools.on_demand.playback_controls.time.monotonic', lambda: clock[0])
    mpv = SimpleNamespace(pause=False, paused_for_cache=False, duration=600, time_pos=120, command=Mock())
    states = []
    controller = OnDemandPlaybackControls(mpv, states.append, 'A title', 'A channel')
    controller.start()
    return controller, mpv, states, clock


def test_controls_auto_hide_hold_pause_and_explicit_dismiss(controls):
    controller, mpv, states, clock = controls
    assert states[-1]['visible']
    clock[0] += 5
    controller.tick()
    assert states[-1]['active'] and not states[-1]['visible']
    count = len(states)
    clock[0] += 1
    controller.tick()
    assert len(states) == count
    mpv.pause = True
    controller.tick(force=True)
    assert states[-1]['visible']
    controller.hide()
    assert not states[-1]['visible']
    controller.interact(holding=True)
    mpv.pause = False
    clock[0] += 12
    controller.tick()
    assert states[-1]['visible']
    controller.interact()
    clock[0] += 5
    controller.tick()
    assert not states[-1]['visible']
    controller.stop()
    assert states[-1] == {'active': False, 'visible': False, 'menu_visible': False}


def test_controls_do_not_update_video_timestamps_when_hidden_or_menu_open(controls):
    controller, mpv, states, clock = controls
    controller.tick()
    assert len(states) == 1  # Quarter-second update limit.
    clock[0] += 5
    controller.tick(menu_visible=True)
    assert len(states) == 1
    controller.tick(force=True)
    assert len(states) == 2 and not states[-1]['visible']


@pytest.mark.parametrize('position,expected', [(-10, 0), (200, 200), (900, 600)])
def test_seek_clamps_to_current_video_without_replacing_mpv(controls, position, expected):
    controller, mpv, states, clock = controls
    assert not controller.seek('previous-video', position)
    mpv.command.assert_not_called()
    assert controller.seek(controller.session_id, position)
    mpv.command.assert_called_once_with('seek', expected, 'absolute+exact')


@pytest.mark.parametrize('position', [float('nan'), float('inf'), 'invalid'])
def test_nonfinite_timeline_seeks_are_ignored(controls, position):
    controller, mpv, states, clock = controls
    assert not controller.seek(controller.session_id, position)
    mpv.command.assert_not_called()


def test_transport_api_validation_and_existing_queue_dispatch(controls):
    controller, mpv, states, clock = controls
    commands = queue.Queue()
    with TestClient(create_app(command_queue=commands, server_conf={})) as client:
        result = client.post('/player/on-demand/seek', json={'session_id': controller.session_id, 'position': 250})
        assert result.status_code == 200
        payload = commands.get_nowait()
        assert payload == {'command': 'on_demand_seek', 'session_id': controller.session_id, 'position': 250}
        player = StationPlayer.__new__(StationPlayer)
        player._on_demand_controls = controller
        assert player.handle_runtime_command_outcome(PlayerOutcome(PlayerState.SUCCESS, payload))
        mpv.command.assert_called_once_with('seek', 250, 'absolute+exact')
        for position in (-1, 'NaN', 'Infinity'):
            assert client.post('/player/on-demand/seek', json={'session_id': 'test', 'position': position}).status_code == 422
        assert client.post('/player/on-demand/controls', json={'session_id': 'test', 'action': 'bad'}).status_code == 422
    with TestClient(create_app(server_conf={})) as client:
        assert client.post('/player/on-demand/seek', json={'session_id': 'test', 'position': 1}).status_code == 503


def test_field_player_preserves_timeline_session_in_runtime_outcome():
    field_player = FieldPlayer(no_server=True)
    field_player._command_queue = queue.Queue()
    payload = {'command': 'on_demand_seek', 'session_id': 'test', 'position': 12}
    field_player._command_queue.put(payload)
    result = field_player._check_input()
    assert result.status == PlayerState.SUCCESS
    assert result.payload == payload


def test_failed_seek_does_not_interrupt_video_playback(controls):
    controller, mpv, states, clock = controls
    mpv.command.side_effect = RuntimeError('Seek is temporarily unavailable')
    player = StationPlayer.__new__(StationPlayer)
    player._l = Mock()
    player._on_demand_controls = controller
    outcome = PlayerOutcome(PlayerState.SUCCESS, {'command': 'on_demand_seek',
        'session_id': controller.session_id, 'position': 20})
    assert player.handle_runtime_command_outcome(outcome)
    assert controller.ready


def test_native_overlay_shows_without_entering_guide_preview_layout():
    window = Mock()
    window.isVisible.return_value = False
    state = {'active': True, 'visible': True, 'title': 'Quote " </script>', 'position': 120}
    app = SimpleNamespace(window=window, playback_state=state)
    WebRenderApp._render_playback_state(app)
    script, world, callback = window.browser.page.return_value.runJavaScript.call_args.args
    assert json.dumps(state) in script
    callback(None)
    window.showFullScreen.assert_called_once_with()
    window.navigate.assert_not_called()
    app.playback_state = {'active': True, 'visible': False}
    WebRenderApp._render_playback_state(app)
    window.browser.page.return_value.runJavaScript.call_args.args[2](None)
    window.hide.assert_called_once_with()
