#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Render a station URL in a Qt WebEngine window, retry failed loads, and respond to queue messages
controlling window visibility and shutdown.
"""
import json
import signal
from queue import Empty

from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QSGRendererInterface
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from fs42.core import logger as project_logger

from fs42.tools.web_channel.display_guard import DisplayGuard
from fs42.tools.web_channel.transition import TransitionWindow

_logger = project_logger.setup('fs42.tools.web_channel.web_render')


class WebRender(QMainWindow):
    """
    Display channel web content in Qt WebEngine with media autoplay and load retries
    """

    def __init__(self, transparent=False):
        """
        Configure the embedded browser's background, autoplay settings, and retry state

        :param transparent: (bool) whether the browser window should allow underlying video to show through
        """
        super(WebRender, self).__init__()
        self.transparent = transparent
        self.browser = QWebEngineView()

        if self.transparent:
            # QWebEngine normally paints an opaque page/background. Make both
            # the top-level window and the browser surface alpha-capable so
            # transparent CSS can reveal the MPV window below.
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.browser.setAttribute(Qt.WA_TranslucentBackground, True)
            self.browser.setStyleSheet('background: transparent;')

        # Configure QWebEngineSettings to enable autoplay
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        # Set custom user agent for identification
        self.browser.page().profile().setHttpUserAgent('FieldStation42-WebRender/1.0')

        # Set page background. Overlay mode needs a real alpha channel so the
        # live MPV channel can show through the guide preview rectangle.
        if self.transparent:
            self.browser.page().setBackgroundColor(QColor(0, 0, 0, 0))
        else:
            self.browser.page().setBackgroundColor(Qt.black)

        self.setCentralWidget(self.browser)

        # Hide cursor
        self.setCursor(Qt.BlankCursor)

        # Retry logic for handling web server startup races
        self.current_url = None
        self.retry_count = 0
        self.max_retries = 3
        self.retry_delay = 2000  # 2 seconds in milliseconds

    def navigate(self, URL):
        """
        Load a channel URL and reset its retry counter
        """
        # Initialize retry tracking for new URL
        self.current_url = URL
        self.retry_count = 0
        _logger.info('WebRender navigating to: {}'.format(URL))

        self.browser.setUrl(QUrl(URL))
        # Connect to loadFinished to simulate user interaction after page loads
        self.browser.loadFinished.connect(self._on_load_finished)

    def _retry_load(self):
        """
        Retry loading the current URL
        """
        _logger.info('WebRender retrying URL: {0} (attempt {1}/{2})'.format(self.current_url, self.retry_count + 1,
                                                                            self.max_retries))
        self.browser.setUrl(QUrl(self.current_url))

    def _on_load_finished(self, success):
        """
        Enable page media after a successful load or schedule retries after a failed load

        :param success: (bool) Qt WebEngine's page-load result
        """
        if success:
            _logger.info('WebRender successfully loaded: {}'.format(self.current_url))
            # Reset retry count on success
            self.retry_count = 0

            # Inject JavaScript to simulate user interaction and enable autoplay
            js_code = """
            (function() {
            // Simulate user interaction to enable autoplay
            document.body.click();

            // Try to enable wake lock and autoplay for media elements
            if ('wakeLock' in navigator) {
                navigator.wakeLock.request('screen').catch(e => console.log('Wake lock failed:', e));
            }

            // Find and try to play any media elements
            const media_elements = document.querySelectorAll('video, audio');
            media_elements.forEach(element => {
                if (element.paused) {
                    element.play().catch(e => console.log('Autoplay failed:', e));
                }
            });
            })();
            """
            self.browser.page().runJavaScript(js_code)
        else:
            # Load failed - hide any error content and show black screen
            hide_error_code = """
            document.body.style.backgroundColor = 'black';
            document.body.innerHTML = '';
            """
            self.browser.page().runJavaScript(hide_error_code)

            # Check if we should retry
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                _logger.error('WebRender load failed for: {0}, will retry in {1}s...'.format(
                    self.current_url, self.retry_delay / 1000))
                # Schedule retry after delay
                QTimer.singleShot(self.retry_delay, self._retry_load)
            else:
                _logger.error('WebRender load failed for: {0} after {1} retries, giving up.'.format(
                    self.current_url, self.max_retries))


class WebRenderApp(QApplication):
    """
    Control a channel browser window through player messages and optional timed refreshes
    """

    def __init__(self, user_conf, queue=None):
        """
        Create the browser window and timers from channel display settings

        :param user_conf: (dict) page geometry, transparency, persistence, and refresh options
        :param queue:     (Queue) optional player messages for window and guide interaction
        """
        super(WebRenderApp, self).__init__([])

        self.queue = queue
        self.user_conf = user_conf
        self.guide_url = user_conf.get('url') or user_conf.get('web_url')
        self.persistent = bool(user_conf.get('persistent', False))
        self.start_hidden = bool(user_conf.get('start_hidden', False))
        self.playback_state = None
        self.windowed = 'width' in user_conf and 'height' in user_conf
        self.window_x = None
        self.window_y = None

        self.backdrop = None
        if user_conf.get('playback_backdrop', False):
            # A separate mapped surface survives MPV VO replacement. labwc
            # places it below playback so an unavailable video reveals black.
            self.backdrop = QMainWindow()
            self.backdrop.setWindowTitle('FieldStation42 Playback Backdrop')
            self.backdrop.setWindowFlags(Qt.FramelessWindowHint)
            self.backdrop.setStyleSheet('background-color: black;')
            self.backdrop.setCursor(Qt.BlankCursor)
            self.backdrop.showFullScreen()

        self.window = WebRender(transparent=bool(user_conf.get('transparent', False)))
        self.reply_queue = user_conf.get('reply_queue')
        self.transition = TransitionWindow() if self.backdrop is not None else None
        self.display_guard = DisplayGuard(self, self._notify_player) if self.backdrop is not None else None
        if self.backdrop is not None:
            self.window.setWindowTitle('FieldStation42 Guide Overlay')
            self.window.resize(self.primaryScreen().geometry().size())
            self.window.browser.loadFinished.connect(self._on_guide_loaded)
            self.primaryScreen().geometryChanged.connect(self._on_screen_geometry)
            self.screenAdded.connect(self._on_preview_screen_added)


        # Set window properties
        if self.windowed:
            width = user_conf['width']
            height = user_conf['height']

            # Always use frameless window (no decorations)
            self.window.setWindowFlags(Qt.FramelessWindowHint)
            self.window.resize(width, height)

            # Calculate position
            if 'x' in user_conf and 'y' in user_conf:
                self.window_x = user_conf['x']
                self.window_y = user_conf['y']
            else:
                screen = self.primaryScreen().availableGeometry()
                self.window_x = screen.center().x() - width // 2
                self.window_y = screen.center().y() - height // 2

        if not self.start_hidden:
            self.show_window()

        # Set up timer for queue processing
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)  # Keep guide overlay commands responsive
        QTimer.singleShot(0, lambda: self._notify_player({'type': 'renderer_ready'}))

        # Set up page refresh timer if configured
        if user_conf.get('refresh_interval', 0) > 0:
            self.refresh_timer = QTimer()
            self.refresh_timer.timeout.connect(self.window.browser.reload)
            self.refresh_timer.start(int(user_conf['refresh_interval'] * 1000))

    def show_window(self):
        """
        Show and focus the browser window and notify page scripts that the guide is visible
        """
        if self.windowed:
            self.window.show()
            if self.window_x is not None and self.window_y is not None:
                self.window.move(self.window_x, self.window_y)
        else:
            self.window.showFullScreen()

        self.window.raise_()
        self.window.activateWindow()
        if self.backdrop is not None:
            self._preview_retries = 0
            QTimer.singleShot(50, self._query_preview_box)

        # Let cached web UIs update themselves after they are already visible.
        self.window.browser.page().runJavaScript(
            "window.dispatchEvent(new CustomEvent('fs42-guide-show'));"
        )

    def hide_window(self):
        """
        Hide the browser window and notify page scripts that the guide is hidden
        """
        self.window.hide()
        if self.transition is not None:
            self.transition.set_preview(None)
        self.window.browser.page().runJavaScript(
            "window.dispatchEvent(new CustomEvent('fs42-guide-hide'));"
        )

    def shutdown_window(self):
        """
        Stop browser timers, close the window, and exit the Qt application
        """
        self.timer.stop()
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        self.window.close()
        if self.transition is not None:
            self.transition.close()
        if self.backdrop is not None:
            self.backdrop.close()
        self.quit()

    def tick(self):
        """
        Handle a queued browser-control message, including guide geometry, visibility, and input
        """
        if self.queue is not None:
            try:
                msg = self.queue.get_nowait()
            except Empty:
                return
            if isinstance(msg, dict) and self._handle_presentation_message(msg):
                return
            if isinstance(msg, dict) and msg.get('type') == 'playback_state':
                self.playback_state = msg['state']
                current_path = QUrl(self.window.current_url or '').path().rstrip('/')
                if self.playback_state.get('active') and current_path not in ('/on-demand', '/static/on_demand/on_demand.html'):
                    url = QUrl(self.window.current_url).resolved(QUrl('/on-demand'))
                    self.window.navigate(url.toString())
                else:
                    self._render_playback_state()
                return
            _logger.info('WebRender received message: {}'.format(msg))
            # Persistent renderers stay alive between open/close operations so
            # QtWebEngine/Chromium only pays its startup cost once.
            if isinstance(msg, dict) and msg.get('type') == 'show_window':
                page = msg.get('page')
                if page == 'on_demand':
                    target_url = QUrl(self.guide_url or self.window.current_url).resolved(QUrl('/on-demand')).toString()
                elif page == 'guide':
                    target_url = self.guide_url
                else:
                    target_url = None
                if target_url and target_url != self.window.current_url:
                    self.window.navigate(target_url)
                geometry = msg.get('preview_geometry') or {}
                if geometry:
                    left = float(geometry.get('left_pct', 0.0))
                    right = float(geometry.get('right_pct', 0.0))
                    top = float(geometry.get('top_pct', 0.0))
                    bottom = float(geometry.get('bottom_pct', 0.0))
                    js = """
                    document.documentElement.style.setProperty(
                        '--live-preview-left', '{:.4f}%'
                    );
                    document.documentElement.style.setProperty(
                        '--live-preview-right', '{:.4f}%'
                    );
                    document.documentElement.style.setProperty(
                        '--live-preview-top', '{:.4f}%'
                    );
                    document.documentElement.style.setProperty(
                        '--live-preview-bottom', '{:.4f}%'
                    );
                    """.format(left, right, top, bottom)
                    self.window.browser.page().runJavaScript(js)

                self.show_window()
                return

            if msg == 'show_window':
                self.show_window()
                return

            if msg == 'hide_window':
                if self.persistent:
                    self.hide_window()
                else:
                    self.shutdown_window()
                return

            if msg == 'shutdown_window':
                self.shutdown_window()
                return
            # Handle key injection commands
            if isinstance(msg, str) and msg.startswith('key:'):
                key_name = msg[4:]
                if key_name not in {
                        'PageUp', 'PageDown', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter',
                        'Escape', 'Backspace', 'Home'
                }:
                    _logger.info("WebRender: rejected disallowed key '{}'".format(key_name))
                    return
                js = "\n                document.dispatchEvent(new KeyboardEvent('keydown', {{\n                    key: '{0}',\n                    code: '{1}',\n                    bubbles: true,\n                    cancelable: true\n                }}));\n                ".format(
                    key_name, key_name)
                self.window.browser.page().runJavaScript(js)
                return


    def _notify_player(self, message):
        """
        Send presentation acknowledgements without blocking the Qt event loop
        """
        if self.reply_queue is not None:
            self.reply_queue.put(message)

    def _on_guide_loaded(self, success):
        """
        Cache the actual transparent panel bounds after the guide loads
        """
        if success:
            if getattr(self, 'playback_state', None) and self.playback_state.get('active'):
                self._render_playback_state()
                return
            self._preview_retries = 0
            self._query_preview_box()

    def _render_playback_state(self):
        """Show only the transport bar over full-size native video, without guide-preview layout."""
        state = self.playback_state or {}
        script = "window.dispatchEvent(new CustomEvent('fs42-playback-state', {detail:" + json.dumps(state) + "}));"
        def rendered(_result):
            if self.playback_state is not state:
                return
            if state.get('active') and state.get('visible'):
                if not self.window.isVisible():
                    self.window.showFullScreen()
                    self.window.raise_()
                    self.window.activateWindow()
            elif not state.get('menu_visible'):
                self.window.hide()
        self.window.browser.page().runJavaScript(script, 0, rendered)

    def _on_preview_screen_added(self, screen):
        """
        Reconnect preview layout after an HDMI output is replaced
        """
        screen.geometryChanged.connect(self._on_screen_geometry)
        self._on_screen_geometry(screen.geometry())

    def _on_screen_geometry(self, geometry):
        """
        Reflow a hidden guide after HDMI resolution changes
        """
        if not self.window.isVisible():
            self.window.resize(min(geometry.width(), 1920), min(geometry.height(), 1080))
        QTimer.singleShot(50, self._query_preview_box)

    def _query_preview_box(self):
        """
        Read panel content coordinates from the rendered guide rather than fixed ratios
        """
        self._preview_retries = getattr(self, '_preview_retries', 0) + 1
        script = """
        (function() {
            const panel = document.getElementById('video-panel');
            if (!panel) return null;
            const rect = panel.getBoundingClientRect();
            const style = getComputedStyle(panel);
            const left = parseFloat(style.borderLeftWidth) || 0;
            const top = parseFloat(style.borderTopWidth) || 0;
            const right = parseFloat(style.borderRightWidth) || 0;
            const bottom = parseFloat(style.borderBottomWidth) || 0;
            return JSON.stringify({x:Math.round(rect.left + left), y:Math.round(rect.top + top),
                    width:Math.round(rect.width - left - right),
                    height:Math.round(rect.height - top - bottom),
                    output_width:window.innerWidth, output_height:window.innerHeight});
        })();
        """
        self.window.browser.page().runJavaScript(script, 0, self._on_preview_box)

    def _on_preview_box(self, box):
        """
        Publish valid panel geometry to the player and retained-frame surface
        """
        if isinstance(box, str):
            try:
                box = json.loads(box)
            except (ValueError, TypeError):
                box = None
        if not isinstance(box, dict) or box.get('width', 0) <= 0 or box.get('height', 0) <= 0:
            if self._preview_retries < 40:
                QTimer.singleShot(100, self._query_preview_box)
            return
        self._notify_player({'type': 'preview_box', 'box': box})
        if self.transition is not None and self.window.isVisible():
            self.transition.set_preview(box)

    def _handle_presentation_message(self, msg):
        """
        Process native frame and display-control messages before browser commands
        """
        if not isinstance(msg, dict):
            return False
        kind = msg.get('type')
        if kind == 'hold_frame' and self.transition is not None:
            token = msg['token']
            callback = lambda: self._notify_player({'type': 'frame_ready', 'token': token})
            if not self.transition.show_frame(msg['path'], callback):
                self._notify_player({'type': 'frame_failed', 'token': token})
            elif msg.get('preview_box'):
                self.transition.set_preview(msg['preview_box'])
            return True
        if kind == 'release_frame' and self.transition is not None:
            self.transition.hide()
            return True
        if kind == 'source_fps' and self.display_guard is not None:
            self.display_guard.set_fps(msg.get('fps'))
            return True
        if kind == 'query_geometry':
            self._query_preview_box()
            return True
        return False


def web_render_runner(user_conf, queue):
    """
    Configure the browser child process and run the channel's Qt event loop

    :param user_conf: (dict) channel URL and browser window settings
    :param queue:     (Queue) incoming control messages from the player
    """

    # Set up signal handler for web process - just exit cleanly
    def web_sigint_handler(sig, frame):
        """
        Exit the browser child process when it receives an interrupt signal
        """
        _logger.info('WebRender process received SIGINT, exiting...')
        import sys
        sys.exit(0)

    signal.signal(signal.SIGINT, web_sigint_handler)

    # Set environment variables to enable autoplay
    import os
    os.environ[
        'QTWEBENGINE_CHROMIUM_FLAGS'] = '--autoplay-policy=no-user-gesture-required --disable-web-security --allow-running-insecure-content --disable-features=VizDisplayCompositor'

    # Set graphics API before creating QApplication
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)

    app = WebRenderApp(user_conf, queue)

    # Navigate to URL after a short delay to ensure Qt is fully initialized
    def delayed_navigate():
        """
        Load the configured page after Qt initialization, falling back to the diagnostics page
        """
        url = user_conf.get('web_url', 'http://localhost:4242/static/diagnostics.html')
        if 'url' in user_conf:
            app.window.navigate(user_conf['url'])
        else:
            app.window.navigate(url)

    QTimer.singleShot(100, delayed_navigate)

    app.exec()


if __name__ == '__main__':
    import sys
    import os
    sys.path.append(os.getcwd())

    # Simple test config - customize as needed
    test_conf = {
        'url': 'http://localhost:4242/static/diagnostics.html',
        'width': 800,
        'height': 600,
        # Uncomment to test specific positioning:
        # "x": 100,
        # "y": 100,
    }

    # Or load a station config by name
    # Uncomment and modify to use a station config:
    # from fs42.core.station_manager import StationManager
    # test_conf = StationManager().station_by_name("diagnostic")

    web_render_runner(test_conf, None)
