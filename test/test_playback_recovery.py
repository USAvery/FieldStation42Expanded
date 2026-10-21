import logging
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fs42 import display_refresh
from fs42.station_player import StationPlayer


MODES = '''HDMI-A-1 "Test display"
  Enabled: yes
  Modes:
    1920x1080 px, 60.000000 Hz (preferred, current)
    1920x1080 px, 50.000000 Hz
'''


class PlaybackRecoveryTests(unittest.TestCase):
    def make_player(self):
        player = StationPlayer.__new__(StationPlayer)
        player.mpv = SimpleNamespace(audio_pts=10.0, audio_params={'samplerate': 48000},
                                     pause=False, paused_for_cache=False, command=Mock())
        player._audio_clock_sample = None
        player._next_audio_clock_check = 0.0
        player._last_audio_reload = 0.0
        player._l = logging.getLogger('recovery-test')
        return player

    def test_stalled_audio_recovers_without_loading_media(self):
        player = self.make_player()
        with patch('fs42.station_player.time.monotonic', side_effect=[100.0, 104.0, 104.0]):
            player._check_audio_clock()
            player._check_audio_clock()
        player.mpv.command.assert_called_once_with('ao-reload')
        self.assertIsNone(player._audio_clock_sample)

    def test_advancing_audio_does_not_reopen(self):
        player = self.make_player()
        with patch('fs42.station_player.time.monotonic', side_effect=[100.0, 104.0]):
            player._check_audio_clock()
            player.mpv.audio_pts = 14.0
            player._check_audio_clock()
        player.mpv.command.assert_not_called()

    def test_paused_or_buffering_audio_does_not_reopen(self):
        for prop in ['pause', 'paused_for_cache']:
            player = self.make_player()
            player._audio_clock_sample = (100.0, 10.0)
            setattr(player.mpv, prop, True)
            with patch('fs42.station_player.time.monotonic', return_value=104.0):
                player._check_audio_clock()
            player.mpv.command.assert_not_called()

    def test_recovery_is_rate_limited(self):
        player = self.make_player()
        player._last_audio_reload = 100.0
        player._audio_clock_sample = (100.0, 10.0)
        with patch('fs42.station_player.time.monotonic', return_value=105.0):
            player._check_audio_clock()
        player.mpv.command.assert_not_called()

    def test_mode_change_reopens_audio_once(self):
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        changed = SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(display_refresh.subprocess, 'run', side_effect=[query, changed]):
            self.assertTrue(display_refresh.match_display_refresh_rate(25, on_mode_change=callback))
        callback.assert_called_once_with()

    def test_unchanged_mode_preserves_audio(self):
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        with patch.object(display_refresh.subprocess, 'run', return_value=query):
            self.assertTrue(display_refresh.match_display_refresh_rate(30, on_mode_change=callback))
        callback.assert_not_called()

    def test_failed_mode_change_preserves_audio(self):
        callback = Mock()
        query = SimpleNamespace(returncode=0, stdout=MODES, stderr='')
        failed = SimpleNamespace(returncode=1, stdout='', stderr='failed')
        with patch.object(display_refresh.subprocess, 'run', side_effect=[query, failed]):
            self.assertFalse(display_refresh.match_display_refresh_rate(25, on_mode_change=callback))
        callback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
