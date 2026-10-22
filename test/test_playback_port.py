#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify relocated playback components preserve the shared display API and cleanup guarantees
"""
import json
import logging
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import mock_open
from types import SimpleNamespace

import pytest

from fs42.tools.field_player.field_player import FieldPlayer
from fs42.tools.field_player.station_player import StationPlayer
from fs42.tools.web_channel.web_render import WebRenderApp


@pytest.mark.parametrize('stale', [False, True])
def test_async_metadata_uses_shared_panel_handle_and_rejects_stale_results(stale):
    """
    Show only metadata belonging to the current playback token through the shared panel API
    """
    player = StationPlayer.__new__(StationPlayer)
    player._metadata_worker = Mock()
    data = object()
    player._metadata_worker.poll.return_value = (8 if stale else 7, data)
    player._metadata_token = 7
    player._metadata_deadline = 110.0
    player.now_playing_panel = None
    player._l = logging.getLogger('metadata-port-test')
    with patch('fs42.tools.field_player.station_player.time.monotonic', return_value=100.0), \
            patch('fs42.tools.media.nfo_agent.show_overlay', return_value='panel') as show:
        player._poll_metadata_overlay()
    if stale:
        show.assert_not_called()
        assert player.now_playing_panel is None
    else:
        show.assert_called_once_with(data, play_duration=10.0)
        assert player.now_playing_panel == 'panel'


def test_mpv_loads_the_relocated_codec_hook_and_keeps_a_persistent_window():
    """
    Resolve the Lua preload hook from the new package and preserve one keep-open MPV process
    """
    player = StationPlayer.__new__(StationPlayer)
    player._start_mpv_managed = True
    player._using_dmabuf_wayland = False
    player._l = logging.getLogger('mpv-port-test')
    with patch('fs42.tools.field_player.station_player.MPV') as mpv, \
            patch('fs42.tools.field_player.station_player.os.path.exists', return_value=True), \
            patch('builtins.open', mock_open(read_data='Raspberry Pi 4 Model B')):
        player._create_mpv(prefer_dmabuf=False)
    mpv.assert_called_once()
    options = mpv.call_args.kwargs
    script = Path(options['script'])
    assert script.is_file()
    assert script.parent.name == 'field_player'
    assert options['keep_open'] == 'always'
    assert options['force_window'] == 'immediate'
    assert 'fs42-playback-pi4=yes' in options['script_opts']


def test_fallback_preserves_the_existing_mpv_client():
    """
    Request compatible decoding without constructing or terminating the persistent MPV client
    """
    player = StationPlayer.__new__(StationPlayer)
    player._start_mpv_managed = True
    player._using_dmabuf_wayland = True
    player._l = logging.getLogger('fallback-port-test')
    player.mpv = Mock()
    original = player.mpv
    with patch('fs42.tools.field_player.station_player.MPV') as create:
        assert player._switch_to_mpv_fallback()
    create.assert_not_called()
    original.terminate.assert_not_called()
    assert player.mpv is original


def test_rendered_guide_geometry_reaches_player_and_transition_surface():
    """
    Decode actual guide content bounds and update both native preview and retained-frame placement
    """
    app = SimpleNamespace(_notify_player=Mock(), transition=Mock(),
                          window=SimpleNamespace(isVisible=lambda: True), _preview_retries=1)
    box = {'x': 1131, 'y': 0, 'width': 789, 'height': 432}
    WebRenderApp._on_preview_box(app, json.dumps(box))
    app._notify_player.assert_called_once_with({'type': 'preview_box', 'box': box})
    app.transition.set_preview.assert_called_once_with(box)


def test_guide_cleanup_failure_still_releases_playback_and_shared_services():
    """
    Release MPV, publish stopped status, and close other services even if guide cleanup raises
    """
    player = FieldPlayer(no_server=True)
    playback = Mock()
    playback._shutdown_guide_overlay.side_effect = RuntimeError('Guide cleanup failed')
    player._player = playback
    player._start_server = Mock()
    player._start_display = Mock()
    player._stop_server = Mock()
    player._stop_display = Mock()
    player._play_stations = Mock(side_effect=RuntimeError('Playback failed'))
    with patch('fs42.tools.field_player.field_player.update_status_socket') as status, \
            patch('fs42.tools.field_player.field_player.signal.signal'):
        with pytest.raises(RuntimeError, match='Guide cleanup failed'):
            player.run()
    playback.shutdown.assert_called_once_with()
    status.assert_called_once_with('stopped', '', -1)
    player._stop_display.assert_called_once_with()
    player._stop_server.assert_called_once_with()
    assert player._player is None
