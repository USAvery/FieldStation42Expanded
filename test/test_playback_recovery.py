#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify audio-clock recovery, HDMI mode repair, and refresh-cadence preservation
"""
import logging
import unittest
from unittest.mock import Mock
from unittest.mock import patch
from types import SimpleNamespace

from fs42.tools.field_player import display_refresh
from fs42.tools.field_player.station_player import StationPlayer


MODES = '''HDMI-A-1 "Test display"
  Enabled: yes
  Modes:
    1920x1080 px, 60.000000 Hz (preferred, current)
    1920x1080 px, 50.000000 Hz
'''


class PlaybackRecoveryTests(unittest.TestCase):
    """
    Verify audio recovery responds to genuine stalls and display changes without reloading media
    """
    def make_player(self):
        """
        Build an isolated MPV clock stub for audio-recovery checks
        """
        player = StationPlayer.__new__(StationPlayer)
        player.mpv = SimpleNamespace(audio_pts=10.0, audio_params={'samplerate': 48000},
                                     pause=False, paused_for_cache=False, command=Mock())
        player._audio_clock_sample = None
        player._next_audio_clock_check = 0.0
        player._last_audio_reload = 0.0
        player._l = logging.getLogger('recovery-test')
        return player

    def test_stalled_audio_recovers_without_loading_media(self):
        """
        Reopen stalled audio output without replacing the active media file
        """
        player = self.make_player()
        with patch('fs42.tools.field_player.station_player.time.monotonic', side_effect=[100.0, 104.0, 104.0]):
            player._check_audio_clock()
            player._check_audio_clock()
        player.mpv.command.assert_called_once_with('ao-reload')
        self.assertIsNone(player._audio_clock_sample)

    def test_advancing_audio_does_not_reopen(self):
        """
        Leave advancing audio output untouched
        """
        player = self.make_player()
        with patch('fs42.tools.field_player.station_player.time.monotonic', side_effect=[100.0, 104.0]):
            player._check_audio_clock()
            player.mpv.audio_pts = 14.0
            player._check_audio_clock()
        player.mpv.command.assert_not_called()

    def test_paused_or_buffering_audio_does_not_reopen(self):
        """
        Avoid recovery while audio is deliberately paused or waiting for buffered data
        """
        for prop in ['pause', 'paused_for_cache']:
            player = self.make_player()
            player._audio_clock_sample = (100.0, 10.0)
            setattr(player.mpv, prop, True)
            with patch('fs42.tools.field_player.station_player.time.monotonic', return_value=104.0):
                player._check_audio_clock()
            player.mpv.command.assert_not_called()

    def test_recovery_is_rate_limited(self):
        """
        Suppress repeated audio reopen attempts during the recovery cooldown
        """
        player = self.make_player()
        player._last_audio_reload = 100.0
        player._audio_clock_sample = (100.0, 10.0)
        with patch('fs42.tools.field_player.station_player.time.monotonic', return_value=105.0):
            player._check_audio_clock()
        player.mpv.command.assert_not_called()

    def test_mode_change_reopens_audio_once(self):
        """
        Notify the player exactly once after a successful refresh-rate change
        """
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        changed = SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(display_refresh.subprocess, 'run', side_effect=[query, changed]):
            self.assertTrue(display_refresh.match_display_refresh_rate(25, on_mode_change=callback))
        callback.assert_called_once_with()

    def test_unchanged_mode_preserves_audio(self):
        """
        Keep audio output open when the current display mode already matches
        """
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        with patch.object(display_refresh.subprocess, 'run', return_value=query):
            self.assertTrue(display_refresh.match_display_refresh_rate(30, on_mode_change=callback))
        callback.assert_not_called()

    def test_failed_mode_change_preserves_audio(self):
        """
        Avoid reopening audio when the compositor rejects a mode change
        """
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        failed = SimpleNamespace(returncode=1, stdout='', stderr='failed')
        with patch.object(display_refresh.subprocess, 'run', side_effect=[query, failed]):
            self.assertFalse(display_refresh.match_display_refresh_rate(25, on_mode_change=callback))
        callback.assert_not_called()

    def test_resolution_guard_ignores_stale_cadence_in_valid_mode(self):
        """
        Preserve a valid display mode even when the guard holds the previous channel cadence
        """
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        with patch.object(display_refresh.subprocess, 'run', return_value=query) as run:
            self.assertTrue(display_refresh.enforce_display_resolution_policy(
                fps=25, on_mode_change=callback))
        run.assert_called_once()
        callback.assert_not_called()

    def test_resolution_repair_uses_source_cadence_once(self):
        """
        Select source cadence when repairing an invalid resolution and notify audio recovery once
        """
        callback = Mock()
        modes = MODES.replace('(preferred, current)', '(preferred)')
        modes += '    3840x2160 px, 30.000000 Hz (current)\n'
        query = SimpleNamespace(returncode=0, stdout=modes, stderr='')
        changed = SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(display_refresh.subprocess, 'run', side_effect=[query, changed]) as run:
            self.assertTrue(display_refresh.enforce_display_resolution_policy(
                fps=25, on_mode_change=callback))
        self.assertIn('1920x1080@50.000000Hz', run.call_args_list[1].args[0])
        callback.assert_called_once_with()

    def test_resolution_repair_without_source_preserves_refresh(self):
        """
        Choose the closest existing refresh rate when repairing resolution without a source cadence
        """
        modes = MODES.replace('(preferred, current)', '(preferred)')
        modes += '    3840x2160 px, 50.000000 Hz (current)\n'
        query = SimpleNamespace(returncode=0, stdout=modes, stderr='')
        changed = SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(display_refresh.subprocess, 'run', side_effect=[query, changed]) as run:
            self.assertTrue(display_refresh.enforce_display_resolution_policy())
        self.assertIn('1920x1080@50.000000Hz', run.call_args_list[1].args[0])


if __name__ == '__main__':
    unittest.main()
