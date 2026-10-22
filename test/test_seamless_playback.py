#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify readiness events, stall recovery, exact preview positioning, and bounded metadata work
"""
import unittest
from unittest.mock import Mock
from unittest.mock import patch
from types import SimpleNamespace

from fs42.tools.field_player import guide_preview
from fs42.tools.field_player.playback_state import PlaybackState


class PlaybackStateTests(unittest.TestCase):
    """
    Verify new-file readiness, playback-clock health, and recovery sampling limits
    """
    def setUp(self):
        """
        Bind readiness callbacks to an isolated MPV stub and initialize playback-health tracking
        """
        self.callbacks = {}
        self.mpv = SimpleNamespace(pause=False, eof_reached=False, time_pos=1.0)
        self.mpv.bind_event = lambda name, callback: self.callbacks.update({name: callback})
        self.state = PlaybackState(self.mpv)

    def test_old_timestamp_does_not_indicate_new_file_ready(self):
        """
        Require a new file-loaded event before accepting the next playback restart
        """
        self.state.begin()
        self.callbacks['playback-restart']({})
        self.assertFalse(self.state.ready)
        self.callbacks['file-loaded']({})
        self.assertFalse(self.state.ready)
        self.callbacks['playback-restart']({})
        self.assertTrue(self.state.ready)

    def test_next_load_discards_previous_readiness(self):
        """
        Clear both readiness events when the next file begins loading
        """
        self.callbacks['file-loaded']({})
        self.callbacks['playback-restart']({})
        self.state.begin()
        self.assertFalse(self.state.ready)
        self.assertFalse(self.state.loaded)

    def test_stalled_local_video_requests_fallback(self):
        """
        Request compatible output after a local playback clock stops advancing
        """
        with patch('fs42.tools.field_player.playback_state.time.monotonic', side_effect=[100.0, 104.0]):
            self.assertIsNone(self.state.check_health(self.mpv))
            self.assertEqual(self.state.check_health(self.mpv), 'fallback')

    def test_stream_allows_refill_before_requesting_reconnect(self):
        """
        Allow the longer stream-refill interval before requesting a reconnect
        """
        with patch('fs42.tools.field_player.playback_state.time.monotonic', side_effect=[100.0, 107.0, 108.0]):
            self.assertIsNone(self.state.check_health(self.mpv, is_stream=True))
            self.assertIsNone(self.state.check_health(self.mpv, is_stream=True))
            self.assertEqual(self.state.check_health(self.mpv, is_stream=True), 'reconnect')

    def test_advancing_video_does_not_recover(self):
        """
        Leave advancing video playback untouched
        """
        with patch('fs42.tools.field_player.playback_state.time.monotonic', side_effect=[100.0, 106.0]):
            self.state.check_health(self.mpv)
            self.mpv.time_pos = 7.0
            self.assertIsNone(self.state.check_health(self.mpv))

    def test_deliberate_pause_and_local_eof_do_not_recover(self):
        """
        Ignore intentional pauses and completed local files during health checks
        """
        for field in ['pause', 'eof_reached']:
            self.mpv.pause = False
            self.mpv.eof_reached = False
            setattr(self.mpv, field, True)
            with patch('fs42.tools.field_player.playback_state.time.monotonic', return_value=104.0):
                self.assertIsNone(self.state.check_health(self.mpv))

    def test_health_sampling_is_rate_limited(self):
        """
        Avoid querying playback health again before the next sample deadline
        """
        with patch('fs42.tools.field_player.playback_state.time.monotonic', side_effect=[100.0, 100.1]):
            self.state.check_health(self.mpv)
            self.mpv.time_pos = 2.0
            self.state.check_health(self.mpv)
        self.assertEqual(self.state._position, 1.0)


class ExactPreviewTests(unittest.TestCase):
    """
    Verify guide previews fit arbitrary aspect ratios and compositor coordinates exactly
    """
    def test_arbitrary_aspects_use_exact_client_size_and_position(self):
        """
        Fit each tested aspect ratio into the guide content rectangle without percentage margins
        """
        box = {'x': 1131, 'y': 0, 'width': 789, 'height': 432,
               'output_width': 1920, 'output_height': 1080}
        for aspect in [4.0 / 3, 16.0 / 9, 1.85, 2.0, 2.35, 2.39, 1.0, 9.0 / 16]:
            player = SimpleNamespace(video_out_params={'aspect': aspect}, fullscreen=True, geometry=None,
                                     video_margin_ratio_left=0, video_margin_ratio_right=0,
                                     video_margin_ratio_top=0, video_margin_ratio_bottom=0)
            selection = {'current': (1920, 1080, 60.0), 'description': 'Samsung'}
            expected = guide_preview._fit_inside(box, aspect)
            with patch.object(guide_preview, '_query_display_selection', return_value=selection), \
                    patch.object(guide_preview, '_trigger_labwc_geometry', return_value=True) as trigger, \
                    patch.object(guide_preview.time, 'sleep'):
                state = guide_preview.apply_guide_preview(player, box=box)
            trigger.assert_called_once_with(expected['x'], expected['y'], logger=None)
            self.assertEqual(player.geometry, '{}x{}'.format(expected['width'], expected['height']))
            self.assertEqual(set(state['preview_geometry'].values()), {0.0})

    def test_binary_compositor_moves_encode_arbitrary_coordinates(self):
        """
        Encode exact horizontal and vertical compositor moves in bounded keyboard actions
        """
        with patch.object(guide_preview.shutil, 'which', return_value='/usr/bin/wtype'), \
                patch.object(guide_preview.subprocess, 'run',
                             return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(guide_preview._trigger_labwc_geometry(1232, 49))
        command = run.call_args[0][0]
        self.assertIn('F20', command)
        self.assertIn('F11', command)
        self.assertIn('ctrl', command)
        self.assertIn('shift', command)

    def test_unrepresentable_coordinates_do_not_move_the_window(self):
        """
        Reject negative or oversized compositor positions without issuing a movement command
        """
        with patch.object(guide_preview.subprocess, 'run') as run:
            self.assertFalse(guide_preview._trigger_labwc_geometry(-1, 0))
            self.assertFalse(guide_preview._trigger_labwc_geometry(4096, 0))
        run.assert_not_called()


class MetadataWorkerTests(unittest.TestCase):
    """
    Verify slow optional metadata reads cannot block playback or preserve obsolete queued work
    """
    def test_obsolete_queued_metadata_is_replaced(self):
        """
        Discard an obsolete queued read and publish the latest media metadata
        """
        import time
        import threading
        from fs42.tools.field_player.metadata_worker import MetadataWorker
        started = threading.Event()
        release = threading.Event()
        calls = []

        def load(path):
            """
            Hold a metadata read until released so the test can exercise bounded work and shutdown
            """
            calls.append(path)
            if path == 'first':
                started.set()
                release.wait(1.0)
            return path

        worker = MetadataWorker(load, Mock())
        try:
            worker.submit('first')
            self.assertTrue(started.wait(1.0))
            worker.submit('obsolete')
            latest = worker.submit('latest')
            release.set()
            deadline = time.monotonic() + 1.0
            result = None
            while time.monotonic() < deadline:
                item = worker.poll()
                if item and item[0] == latest:
                    result = item
                    break
                time.sleep(0.002)
            self.assertEqual(result, (latest, 'latest'))
            self.assertEqual(calls, ['first', 'latest'])
        finally:
            release.set()
            worker.stop()

    def test_worker_shutdown_does_not_wait_for_slow_metadata(self):
        """
        Return from metadata-worker shutdown without waiting for a slow read
        """
        import time
        import threading
        from fs42.tools.field_player.metadata_worker import MetadataWorker
        started = threading.Event()
        release = threading.Event()

        def load(path):
            """
            Hold a metadata read until released so the test can exercise bounded work and shutdown
            """
            started.set()
            release.wait(1.0)

        worker = MetadataWorker(load, Mock())
        worker.submit('slow')
        self.assertTrue(started.wait(1.0))
        before = time.monotonic()
        worker.stop()
        self.assertLess(time.monotonic() - before, 0.05)
        release.set()

if __name__ == '__main__':
    unittest.main()
