"""Verify shared action contracts, transport adapters, and context-aware dispatch."""
import json
import importlib
import queue
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from fs42.core.controls import ACTIONS, KEY_ACTIONS, control_manifest
from fs42.tools.field_player.field_player import FieldPlayer
from fs42.tools.field_player.station_player import StationPlayer, PlayerOutcome
from fs42.tools.field_player._constants import PlayerState
from fs42.web.app import create_app
from fs42.web.remote_app import create_app as create_remote


@pytest.mark.parametrize('action,arguments,message', [
    ('navigation.up', {}, {'command': 'web_key', 'key': 'ArrowUp'}),
    ('navigation.back', {}, {'command': 'web_key', 'key': 'Escape'}),
    ('playback.play_pause', {}, {'command': 'mpv_command', 'action': 'play_pause'}),
    ('playback.seek_relative', {'seconds': -30}, {'command': 'mpv_seek', 'seconds': -30}),
    ('playback.seek', {'session_id': 'video', 'position': 90},
     {'command': 'on_demand_seek', 'session_id': 'video', 'position': 90}),
    ('playback.controls', {'session_id': 'video', 'action': 'hold'},
     {'command': 'on_demand_controls', 'session_id': 'video', 'action': 'hold'}),
    ('menu.guide', {}, {'command': 'guide'}),
    ('menu.on_demand', {}, {'command': 'on_demand_menu'}),
    ('channel.tune', {'channel': 21}, {'command': 'direct', 'channel': 21}),
    ('channel.next', {}, {'command': 'up'}),
    ('parental.digit', {'digit': '7'}, {'command': 'parental_digit', 'digit': '7'}),
    ('player.stop', {}, {'command': 'exit'}),
])
def test_semantic_controls_dispatch_validated_queue_messages(action, arguments, message):
    commands = queue.Queue()
    with TestClient(create_app(command_queue=commands, server_conf={})) as client:
        result = client.post('/controls/dispatch', json={'action': action, 'arguments': arguments})
        assert result.status_code == 200
        assert result.json()['action'] == action
        assert commands.get_nowait() == message
        assert commands.empty()


@pytest.mark.parametrize('payload', [
    {'action': 'not-a-control'},
    {'action': 'navigation.up', 'arguments': {'command': 'exit'}},
    {'action': 'playback.seek_relative'},
    {'action': 'playback.seek_relative', 'arguments': {'seconds': 'Infinity'}},
    {'action': 'playback.seek', 'arguments': {'session_id': 'old', 'position': -1}},
    {'action': 'channel.tune', 'arguments': {'channel': True}},
    {'action': 'parental.digit', 'arguments': {'digit': '123'}},
    {'action': 'volume.up', 'arguments': {'service': '__dict__'}},
    {'action': 'navigation.up', 'extra': 'ignored?'},
])
def test_controls_reject_unknown_actions_and_invalid_arguments_before_dispatch(payload):
    commands = queue.Queue()
    with TestClient(create_app(command_queue=commands, server_conf={})) as client:
        assert client.post('/controls/dispatch', json=payload).status_code == 422
        assert commands.empty()


def test_disconnected_controls_report_failure_and_volume_uses_existing_provider():
    with TestClient(create_app(server_conf={})) as client:
        assert client.post('/controls/dispatch', json={'action': 'navigation.back'}).status_code == 503
    from unittest.mock import AsyncMock
    with TestClient(create_app(server_conf={})) as client, \
            patch('fs42.web.blueprints.api.player.volume_up', new=AsyncMock(return_value={'volume': 0})) as volume:
        assert client.post('/controls/dispatch', json={'action': 'volume.up'}).json()['result'] == {'volume': 0}
        volume.assert_awaited_once_with()


def test_standalone_transport_advertises_and_dispatches_only_supported_controls():
    with TestClient(create_remote()) as client:
        actions = client.get('/controls').json()['actions']
        assert set(actions) == {'channel.next', 'channel.previous', 'channel.tune', 'menu.on_demand'}
        with patch('fs42.tools.field_player.remote_commands.write_command', return_value={'channel': 21}) as write:
            result = client.post('/controls/dispatch', json={'action': 'channel.tune', 'arguments': {'channel': 21}})
            assert result.json()['result'] == {'channel': 21}
            write.assert_called_once_with({'command': 'direct', 'channel': 21})
            assert client.post('/controls/dispatch', json={'action': 'playback.play_pause'}).status_code == 503
            assert write.call_count == 1


def test_action_keys_are_unique_and_only_public_metadata_reaches_clients():
    keys = [key for action in ACTIONS.values() for key in action.keys]
    assert len(keys) == len(set(keys))
    assert set(KEY_ACTIONS.values()) <= set(ACTIONS)
    assert KEY_ACTIONS['Escape'] == KEY_ACTIONS['Backspace'] == 'navigation.back'
    manifest = control_manifest()
    assert set(manifest['actions']) == set(ACTIONS)
    assert all(set(action) == {'label', 'arguments'} for action in manifest['actions'].values())


def test_queue_channel_commands_keep_order_and_do_not_overwrite_a_command_file():
    field_player = FieldPlayer(no_server=True)
    field_player._command_queue = queue.Queue()
    for command in ('up', 'up', 'down'):
        field_player._command_queue.put({'command': command})
    for command in ('up', 'up', 'down'):
        result = field_player._check_input()
        assert result.status == PlayerState.CHANNEL_CHANGE
        assert json.loads(result.payload) == {'command': command}


def test_relative_seek_routes_without_interrupting_the_current_player():
    player = StationPlayer.__new__(StationPlayer)
    player.mpv = Mock()
    player._l = Mock()
    player._on_demand_controls = Mock()
    player._tick_on_demand_controls = Mock()
    result = PlayerOutcome(PlayerState.SUCCESS, {'command': 'mpv_seek', 'seconds': 30})
    assert player.handle_runtime_command_outcome(result)
    player.mpv.command.assert_called_once_with('seek', 30, 'relative+exact')
    player._on_demand_controls.interact.assert_called_once_with()
    assert player.handle_runtime_command_outcome(PlayerOutcome(PlayerState.SUCCESS, {'command': 'mpv_seek', 'seconds': 'NaN'}))
    assert player.mpv.command.call_count == 1


def test_navigation_context_is_resolved_by_player_not_stale_client_status():
    player = StationPlayer.__new__(StationPlayer)
    player.guide_visible = True
    player.guide_process = Mock()
    player.guide_queue = queue.Queue()
    player._on_demand_controls = None
    player._l = Mock()
    outcome = PlayerOutcome(PlayerState.SUCCESS, 'web_key:ArrowUp')
    assert player.handle_runtime_command_outcome(outcome)
    assert player.guide_queue.get_nowait() == 'key:ArrowUp'
    player.guide_visible = False
    assert not player.handle_runtime_command_outcome(outcome)
    player._on_demand_controls = Mock()
    player._tick_on_demand_controls = Mock()
    assert player.handle_runtime_command_outcome(outcome)
    assert player.guide_queue.get_nowait() == 'key:ArrowUp'


@pytest.mark.parametrize('key,action', [('ArrowUp', 'navigation.up'), ('Backspace', 'navigation.back'), (' ', 'playback.play_pause')])
def test_physical_remote_uses_shared_actions_without_a_guide_channel(monkeypatch, key, action):
    monkeypatch.setitem(sys.modules, 'evdev', SimpleNamespace(ecodes=Mock(), InputDevice=Mock()))
    remote = importlib.import_module('fs42.tools.remote_control.remote_control')
    with patch.object(remote.requests, 'post', return_value=Mock(ok=True)) as post:
        assert remote.send_custom_guide_key(key)
        post.assert_called_once_with(remote.FS42_BASE_URL + '/controls/dispatch',
                                     json={'action': action, 'arguments': {}}, timeout=2)


def test_geometry_navigation_handles_grids_lists_hidden_and_dynamic_controls():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for browser utility checks')
    source = Path('fs42/web/static/utils/navigation.js').read_text()
    script = r"""
const assert=require('assert'),vm=require('vm');
vm.runInThisContext(__SOURCE__);
const item=(x,y,width=100,height=40,disabled=false)=>({disabled,
    getBoundingClientRect:()=>({left:x,right:x+width,top:y,bottom:y+height,width,height})});
let items=[item(0,0),item(120,0),item(240,0),item(0,60),item(120,60),item(240,60),item(0,120,340)];
let selected=1;
const nav=new SpatialNavigator({getItems:()=>items,getSelected:()=>selected,onSelect:i=>selected=i});
nav.move('down');assert.equal(selected,4);
nav.move('right');assert.equal(selected,5);
nav.move('right');assert.equal(selected,5); // keep selection at the edge
nav.move('down');assert.equal(selected,6); // full-width footer
nav.move('up');assert.equal(selected,4);
items=[item(0,0),item(0,40),item(0,80),item(0,120)];selected=1;
nav.move('down');assert.equal(selected,2); // same navigator, single-column layout
items[3].disabled=true;
nav.move('down');assert.equal(selected,2);
items[0]=item(0,0,0,0);nav.selectFirst();assert.equal(selected,1);
nav.selectLast();assert.equal(selected,2);
items.push(item(0,160));nav.move('down');assert.equal(selected,4); // added after setup
items=[];assert.equal(nav.selectFirst(),-1);assert.equal(nav.selectLast(),-1);
"""
    result = subprocess.run([node, '-'], input=script.replace('__SOURCE__', json.dumps(source)),
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
