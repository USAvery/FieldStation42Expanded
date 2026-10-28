#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Check package boundaries and relocated integration entry points
"""
import os
import ast
import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fs42.core import paths
from fs42.web.remote_app import create_app


def test_source_root_has_only_responsibility_packages():
    """
    Keep platform and feature packages within the uniform taxonomy
    """
    directory = os.path.join(paths.PROJECT_ROOT, 'fs42')
    packages = {
        name
        for name in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, name)) and not name.startswith('_')
    }
    assert packages == {'core', 'tools', 'web'}


@pytest.mark.parametrize('module', [
    'fs42.tools.osd.main',
    'fs42.tools.osd.display.logo_display',
    'fs42.tools.overlay.display.now_playing_display',
    'fs42.tools.overlay.display.parental_controls_display',
    'fs42.tools.overlay.display.ticker_display',
    'fs42.tools.diagnostics.diagnostic_tk',
    'fs42.tools.web_channel.web_render',
    'fs42.tools.cable_box.main',
    'fs42.tools.remote_control.main',
])
def test_relocated_integrations_import(module):
    """
    Resolve integration entry points without starting devices or displays
    """
    assert importlib.import_module(module) is not None


def test_remote_page_and_legacy_assets_work_outside_repo(tmp_path, monkeypatch):
    """
    Serve the remote independently of the working directory
    """
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app()) as client:
        for url in ('/', '/static/index.html'):
            response = client.get(url)
            assert response.status_code == 200
            assert 'app.web_interface.handheld_remote.setup()' in response.text
        for url in ('/static/remote.js', '/static/remote.css', '/static/tools/handheld_remote/handheld_remote.js',
                    '/static/tools/handheld_remote/style.css',
                    '/static/web_interface/handheld_remote/handheld_remote.js',
                    '/static/web_interface/handheld_remote/style.css'):
            assert client.get(url).status_code == 200


def test_remote_api_dispatches_and_preserves_validation():
    """
    Forward validated commands to the player transport and return its status
    """
    current = {'channel': 12, 'name': 'Example', 'title': 'Program'}
    with TestClient(create_app()) as client:
        with patch('fs42.tools.field_player.remote_commands.write_command', return_value=current) as write:
            response = client.post('/api/command', json={'command': 'direct', 'channel': 12})
            assert response.json() == {'status': 'ok', 'current': current}
            write.assert_called_once_with({'command': 'direct', 'channel': 12})
            assert client.post('/api/command', json={'command': 'invalid', 'channel': 12}).status_code == 422
            assert write.call_count == 1
        with patch('fs42.tools.field_player.remote_commands.read_status', return_value=current):
            assert client.get('/api/status').json() == current


def test_player_command_transport_uses_existing_file_protocol(tmp_path, monkeypatch):
    """
    Keep the standalone remote's channel and status file formats
    """
    import json
    from fs42.tools.field_player import remote_commands
    command_path = os.path.join(str(tmp_path), 'channel.socket')
    status_path = os.path.join(str(tmp_path), 'play_status.socket')
    with open(command_path, 'w') as f_out:
        f_out.write('')
    with open(status_path, 'w') as f_out:
        json.dump({'channel_number': 12, 'network_name': 'Example', 'title': 'Program'}, f_out)
    monkeypatch.setattr(remote_commands, 'SOCKET_PATH', command_path)
    monkeypatch.setattr(remote_commands, 'STATUS_SOCKET_PATH', status_path)
    with patch('fs42.tools.field_player.remote_commands.time.sleep'):
        result = remote_commands.write_command({'command': 'direct', 'channel': 12})
    assert result == {'channel': 12, 'name': 'Example', 'title': 'Program'}
    with open(command_path) as f_in:
        assert json.load(f_in) == {'command': 'direct', 'channel': 12}


def test_firmware_remains_independently_deployable():
    """
    Keep the Pico program free of desktop package imports
    """
    filename = os.path.join(paths.PROJECT_ROOT, 'fs42', 'tools', 'cable_box', 'firmware', 'aerial_listener.py')
    with open(filename, encoding='utf8') as f_in:
        tree = ast.parse(f_in.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or '').startswith('fs42')
        if isinstance(node, ast.Import):
            assert not any(alias.name.startswith('fs42') for alias in node.names)
