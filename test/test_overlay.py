#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Verify overlay drawing, metadata fallback, queue handling, ticker completion, and child-process cleanup
"""
import os
import sys
import json
import queue
import sqlite3
import subprocess
from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication

from fs42.core.paths import PROJECT_ROOT
from fs42.tools.overlay import _constants
from fs42.tools.overlay.overlay import Overlay
from fs42.tools.overlay._utils import OverlayError
from fs42.tools.overlay.display.ticker_display import TickerDisplay
from fs42.tools.overlay.display.now_playing_display import NowPlayingDisplay
from fs42.tools.overlay.display.parental_controls_display import ParentalControlsDisplay


@pytest.fixture(scope='module')
def qt_app():
    """
    Keep Qt available for font metrics, timers, and offscreen window rendering
    """
    return QApplication.instance() or QApplication([])


@pytest.fixture
def metadata_db(tmp_path):
    """
    Store one track in a real metadata cache for overlay lookup and fallback checks
    """
    path = tmp_path / 'metadata.db'
    track = str(tmp_path / 'Track.mp3')
    with sqlite3.connect(str(path)) as connection:
        connection.execute('CREATE TABLE file_meta (path TEXT, meta TEXT)')
        connection.execute('INSERT INTO file_meta VALUES (?, ?)',
                           (track, json.dumps({'title': 'Track Title', 'artist': 'Artist', 'album': 'Album'})))
    return track, str(path)


def test_audio_metadata_and_filename_fallback(qt_app, metadata_db, tmp_path):
    """
    Show stored audio fields and derive the title from the filename when no cache row exists
    """
    track, database = metadata_db
    display = NowPlayingDisplay(track, database)
    fallback = NowPlayingDisplay(str(tmp_path / 'Another Track.mp3'), database)
    try:
        assert display._metadata['title'] == 'Track Title'
        assert display._metadata['artist'] == 'Artist'
        assert display._metadata['album'] == 'Album'
        assert fallback._metadata['title'] == 'Another Track'
        assert fallback._metadata['artist'] == ''
        assert not display._timer.isActive()
        assert not fallback._timer.isActive()
    finally:
        display.close()
        fallback.close()


def test_parental_messages_update_prompt_and_finish(qt_app):
    """
    Drain digit and error updates, then stop polling and signal completion on a close request
    """
    messages = queue.Queue()
    display = ParentalControlsDisplay('Station', messages, 'unknown')
    finished = Mock()
    display.finished.connect(finished)
    try:
        messages.put({'digits': 2})
        display._poll_queue()
        assert display._digits == 2
        assert not display._error
        messages.put({'digits': 0, 'error': True})
        display._poll_queue()
        assert display._digits == 0
        assert display._error
        assert display._theme['box'].getRgb() == _constants.PARENTAL_THEMES['classic']['box']
        messages.put({'close': True})
        display._poll_queue()
        finished.assert_called_once_with()
        assert not display._timer.isActive()
    finally:
        display.close()


def test_ticker_finishes_only_after_requested_repeats(qt_app):
    """
    Count complete scrolls and stop the animation after the final requested repetition
    """
    display = TickerDisplay('Announcement', iterations=2)
    finished = Mock()
    display.finished.connect(finished)
    try:
        width = QFontMetrics(display._font).horizontalAdvance('Announcement')
        display._scroll_position = -width
        display._scroll_text()
        assert display._current_iterations == 1
        assert display._timer.isActive()
        finished.assert_not_called()
        display._scroll_position = -width
        display._scroll_text()
        finished.assert_called_once_with()
        assert not display._timer.isActive()
    finally:
        display.close()


def test_empty_ticker_exits_instead_of_leaving_a_blank_process(qt_app):
    """
    Finish an empty announcement on its first update
    """
    display = TickerDisplay('')
    finished = Mock()
    display.finished.connect(finished)
    try:
        display._scroll_text()
        finished.assert_called_once_with()
        assert not display._timer.isActive()
    finally:
        display.close()


def test_ticker_logo_loads_outside_repository(qt_app, tmp_path, monkeypatch):
    """
    Resolve the optional ticker logo from the project runtime directory regardless of working directory
    """
    logo_path = tmp_path / 'logo.png'
    image = QImage(100, 100, QImage.Format_ARGB32)
    image.fill(Qt.white)
    assert image.save(str(logo_path))
    monkeypatch.setattr(_constants, 'TICKER_LOGO_PATH', str(logo_path))
    directory = tmp_path / 'elsewhere'
    directory.mkdir()
    monkeypatch.chdir(directory)
    display = TickerDisplay('Message')
    try:
        assert display._logo is not None
        assert display._logo.height() == int(_constants.TICKER_HEADER_HEIGHT * 0.8)
    finally:
        display.close()


@pytest.mark.parametrize('kind,theme', [('ticker', name) for name in _constants.TICKER_THEMES]
                         + [('parental_controls', name) for name in _constants.PARENTAL_THEMES]
                         + [('ticker', 'unknown'), ('now_playing', None)])
def test_displays_render_and_preserve_player_input(qt_app, metadata_db, kind, theme):
    """
    Render each theme with transparent window corners and keep focus and mouse input with the player
    """
    if kind == 'ticker':
        display = TickerDisplay('A scrolling announcement', style=theme)
    elif kind == 'parental_controls':
        display = ParentalControlsDisplay('Station', queue.Queue(), theme)
    else:
        display = NowPlayingDisplay(*metadata_db)
    try:
        image = QImage(display.size(), QImage.Format_ARGB32)
        image.fill(0)
        display.render(image)
        assert image.pixelColor(0, 0).alpha() == 0
        assert any(image.pixelColor(x, y).alpha() for x in range(0, image.width(), 5)
                   for y in range(0, image.height(), 5))
        assert display.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert display.windowFlags() & Qt.WindowDoesNotAcceptFocus
    finally:
        display.close()
    assert not display._timer.isActive()


def test_ticker_lock_is_exclusive_and_released(qt_app, tmp_path, monkeypatch):
    """
    Reject a second ticker while allowing independent overlays and reclaim the lock after cleanup
    """
    monkeypatch.setattr('fs42.tools.overlay.overlay.tempfile.gettempdir', lambda: str(tmp_path))
    first = Overlay('ticker', text='First')
    second = Overlay('ticker', text='Second')
    other = Overlay('now_playing')
    try:
        assert first._acquire_lock()
        assert not second._acquire_lock()
        second._cleanup()
        assert not second._acquire_lock()
        assert other._acquire_lock()
        first._cleanup()
        assert second._acquire_lock()
    finally:
        first._cleanup()
        second._cleanup()
        other._cleanup()


def test_unknown_overlay_is_rejected_before_launch():
    """
    Report an invalid overlay selection before allocating a window or child process
    """
    with pytest.raises(OverlayError, match='Unknown overlay type'):
        Overlay('missing')


def test_spawned_overlays_follow_their_expected_lifetimes(tmp_path):
    """
    Launch real spawned processes and verify PIN closure, ticker exclusion, and persistent audio display
    """
    code = r'''
import os
import time
import tempfile
import multiprocessing
from fs42.tools.overlay import run_ticker
from fs42.tools.overlay import run_now_playing
from fs42.tools.overlay import run_parental_controls
from fs42.tools.overlay._constants import TICKER_LOCK_KEY

if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')
    children = []
    messages = multiprocessing.Queue()
    try:
        ticker = run_ticker('')
        children.append(ticker)
        ticker.join(10)
        assert ticker.exitcode == 0, ('empty ticker', ticker.exitcode)
        audio = run_now_playing('Track.mp3', os.path.join(tempfile.gettempdir(), 'metadata.db'))
        children.append(audio)
        time.sleep(2)
        assert audio.is_alive(), ('audio exited early', audio.exitcode)
        prompt = run_parental_controls('Station', messages)
        children.append(prompt)
        messages.put({'digits': 2})
        messages.put({'error': True, 'digits': 0})
        messages.put({'close': True})
        prompt.join(10)
        assert prompt.exitcode == 0, ('prompt did not close', prompt.exitcode)
        ticker = run_ticker('Keep this ticker running')
        children.append(ticker)
        lock = os.path.join(tempfile.gettempdir(), TICKER_LOCK_KEY + '.lock')
        deadline = time.monotonic() + 10
        while not os.path.exists(lock) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert os.path.exists(lock), 'ticker did not claim its lock'
        duplicate = run_ticker('')
        children.append(duplicate)
        duplicate.join(10)
        assert duplicate.exitcode == 1, ('duplicate ticker', duplicate.exitcode)
        assert ticker.is_alive()
        assert audio.is_alive()
        ticker.terminate()
        ticker.join(5)
        assert not ticker.is_alive()
        replacement = run_ticker('')
        children.append(replacement)
        replacement.join(10)
        assert replacement.exitcode == 0, ('ticker lock was not reclaimed', replacement.exitcode)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
        messages.close()
        messages.join_thread()
print('Overlay processes completed their lifecycle checks')
'''
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', TMP=str(tmp_path), TEMP=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', code], cwd=PROJECT_ROOT, env=environment,
                            capture_output=True, text=True, timeout=50)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('arguments', [['--help'], ['ticker', '--help'], ['now_playing', '--help']])
def test_command_line_help(arguments):
    """
    Describe overlay inputs without opening a Qt window
    """
    result = subprocess.run([sys.executable, '-m', 'fs42.tools.overlay.main'] + arguments,
                            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout
