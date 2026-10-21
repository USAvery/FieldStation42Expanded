#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Exercise OSD configuration, status polling, visibility, and rendering without a physical display
"""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QImage
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication

from fs42.tools.osd import _api
from fs42.tools.osd.osd import OsdWindow
from fs42.tools.osd._constants import ContentType
from fs42.tools.osd._constants import LogoDisplayConfig
from fs42.tools.osd._constants import StatusDisplayConfig
from fs42.tools.osd._constants import VolumeDisplayConfig
from fs42.tools.osd.display.logo_display import LogoDisplay
from fs42.tools.osd.display.status_display import StatusDisplay
from fs42.tools.osd.display.volume_display import VolumeDisplay


@pytest.fixture(scope='module')
def qt_app():
    """
    Keep a Qt application alive while display fonts and pixmaps are in use
    """
    return QApplication.instance() or QApplication([])


@pytest.fixture
def status_file(tmp_path):
    """
    Provide an isolated player status file containing a playing feature
    """
    path = tmp_path / 'status.json'
    path.write_text(json.dumps({'network_name': 'Example', 'channel_number': 4,
                                'status': 'playing', 'title': 'Program', 'content_type': 'feature'}))
    return str(path)


@pytest.mark.parametrize('content', ['', '{', 'null', '[]', '42', '"text"'])
def test_invalid_status_preserves_text(qt_app, status_file, content):
    """
    Retain the last channel text when a status update is incomplete or is not a JSON object
    """
    display = StatusDisplay(StatusDisplayConfig(socket_file=status_file))
    Path(status_file).write_text(content)
    display.update(1.0)
    assert display._string == '4 - Example'
    assert display.time_since_change == 1.0


def test_status_expires_and_playback_change_restores_it(qt_app, status_file):
    """
    Redisplay unchanged channel text when playback state changes after the timer expires
    """
    display = StatusDisplay(StatusDisplayConfig(socket_file=status_file))
    assert display.is_visible()
    display.update(3.0)
    assert not display.is_visible()
    data = json.loads(Path(status_file).read_text())
    data['status'] = 'stopped'
    Path(status_file).write_text(json.dumps(data))
    display.update(0.1)
    assert display.is_visible()
    assert display._color.getRgb() == display.config.text_color


@pytest.mark.parametrize('volume,expected', [('MUTED (75%)', 0.75), ('150%', 1.0), ('0%', 0.0)])
def test_volume_consumes_configured_file(qt_app, tmp_path, volume, expected):
    """
    Read and clear the configured mixer file once, then expire the displayed level
    """
    path = tmp_path / 'volume.json'
    display = VolumeDisplay(VolumeDisplayConfig(socket_file=str(path)))
    assert not display.is_visible()
    path.write_text(json.dumps({'volume': volume}))
    display.update(0.1)
    assert display.volume == expected
    assert display.is_visible()
    assert path.read_text() == ''
    display.update(6.0)
    assert not display.is_visible()


def test_factory_defaults_and_hybrid(qt_app, tmp_path, monkeypatch, status_file):
    """
    Supply default status and volume displays and expand hybrid entries without duplicate meters
    """
    path = tmp_path / 'osd.json'
    monkeypatch.setattr(_api, 'CONFIG_FILE_PATH', str(path))
    monkeypatch.setattr('fs42.tools.osd.display.logo_display.StationManager', Mock)
    displays = _api.load_objects()
    assert [type(item) for item in displays] == [StatusDisplay, VolumeDisplay]
    path.write_text(json.dumps([{'type': 'HybridDisplay', 'socket_file': status_file,
                                'text_color': [1, 2, 3, 255]}]))
    displays = _api.load_objects()
    assert [type(item) for item in displays] == [LogoDisplay, StatusDisplay, VolumeDisplay]
    assert displays[-1].config.color == (1, 2, 3, 255)
    path.write_text(json.dumps([{'type': 'VolumeDisplay'}]))
    assert len(_api.load_objects()) == 1


def test_logo_visibility_cache_and_feature_resume(qt_app, tmp_path, status_file, monkeypatch):
    """
    Cache a loaded fallback logo, hide it during breaks, and restart timing when its feature resumes
    """
    monkeypatch.setattr('fs42.tools.osd.display.logo_display.StationManager', Mock)
    image = QImage(20, 20, QImage.Format_ARGB32)
    image.fill(0xff00ff00)
    path = tmp_path / 'logo.png'
    assert image.save(str(path))
    display = LogoDisplay(LogoDisplayConfig(socket_file=status_file, default_logo=str(path)))
    assert display.is_visible()
    assert display.current_logo_path == str(path)
    frames = display.current_logo_frames
    display.load_logo_for_channel(display.current_channel_info)
    assert display.current_logo_frames is frames
    display.update(6.0)
    assert not display.is_visible()
    display.config.default_logo_permanent = True
    assert display.is_visible()
    data = json.loads(Path(status_file).read_text())
    data['content_type'] = 'commercial'
    Path(status_file).write_text(json.dumps(data))
    display.update(0.1)
    assert not display.is_visible()
    data['content_type'] = 'feature'
    Path(status_file).write_text(json.dumps(data))
    display.update(0.1)
    assert display.is_visible()
    assert display.time_since_change == 0.0


def test_window_visibility_animation_and_painting(qt_app, status_file, monkeypatch):
    """
    Paint each display and adjust window polling as content becomes animated or hidden
    """
    monkeypatch.setattr('fs42.tools.osd.display.logo_display.StationManager', Mock)
    status = StatusDisplay(StatusDisplayConfig(socket_file=status_file))
    volume = VolumeDisplay(VolumeDisplayConfig(socket_file=status_file))
    volume.volume = 0.5
    volume.time_since_change = 0.0
    logo = LogoDisplay(LogoDisplayConfig(socket_file=status_file))
    frame = QPixmap(20, 20)
    frame.fill()
    logo.current_logo_frames = [frame, frame]
    logo.current_frame_durations = [0.1, 0.1]
    logo.current_content_type = ContentType.FEATURE
    logo.time_since_change = 0.0
    image = QImage(640, 480, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        for display in (status, volume, logo):
            display.draw(painter, 640, 480)
    finally:
        painter.end()
    assert any(image.pixelColor(x, y).alpha() for x in range(640) for y in range(480))
    window = OsdWindow([logo])
    try:
        window._tick()
        assert window.isVisible()
        assert window.timer.interval() == 100
        logo.is_animated = True
        logo.update(0.11)
        assert logo.current_frame_index == 1
        window._tick()
        assert window.timer.interval() == 33
        logo.time_since_change = 10.0
        window._tick()
        assert not window.isVisible()
        assert window.timer.interval() == 250
    finally:
        window.timer.stop()
        window.close()
