import signal
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

class WebRender(QMainWindow):
    def __init__(self, transparent=False):
        super().__init__()
        self.transparent = transparent
        self.browser = QWebEngineView()

        if self.transparent:
            # QWebEngine normally paints an opaque page/background. Make both
            # the top-level window and the browser surface alpha-capable so
            # transparent CSS can reveal the MPV window below.
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.browser.setAttribute(Qt.WA_TranslucentBackground, True)
            self.browser.setStyleSheet("background: transparent;")

        # Configure QWebEngineSettings to enable autoplay
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

        # Set custom user agent for identification
        self.browser.page().profile().setHttpUserAgent("FieldStation42-WebRender/1.0")

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

    def navigate(self, URL: str):
        # Initialize retry tracking for new URL
        self.current_url = URL
        self.retry_count = 0
        print(f"WebRender navigating to: {URL}")

        self.browser.setUrl(QUrl(URL))
        # Connect to loadFinished to simulate user interaction after page loads
        self.browser.loadFinished.connect(self._on_load_finished)

    def _retry_load(self):
        """Retry loading the current URL"""
        print(f"WebRender retrying URL: {self.current_url} (attempt {self.retry_count + 1}/{self.max_retries})")
        self.browser.setUrl(QUrl(self.current_url))

    def _on_load_finished(self, success):
        if success:
            print(f"WebRender successfully loaded: {self.current_url}")
            # Reset retry count on success
            self.retry_count = 0

            # Inject JavaScript to simulate user interaction and enable autoplay
            js_code = """
            // Simulate user interaction to enable autoplay
            document.body.click();

            // Try to enable wake lock and autoplay for media elements
            if ('wakeLock' in navigator) {
                navigator.wakeLock.request('screen').catch(e => console.log('Wake lock failed:', e));
            }

            // Find and try to play any media elements
            const mediaElements = document.querySelectorAll('video, audio');
            mediaElements.forEach(element => {
                if (element.paused) {
                    element.play().catch(e => console.log('Autoplay failed:', e));
                }
            });
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
                print(f"WebRender load failed for: {self.current_url}, will retry in {self.retry_delay/1000}s...")
                # Schedule retry after delay
                QTimer.singleShot(self.retry_delay, self._retry_load)
            else:
                print(f"WebRender load failed for: {self.current_url} after {self.max_retries} retries, giving up.")

class WebRenderApp(QApplication):
    def __init__(self, user_conf, queue=None):
        super().__init__([])

        self.queue = queue
        self.user_conf = user_conf
        self.persistent = bool(user_conf.get("persistent", False))
        self.start_hidden = bool(user_conf.get("start_hidden", False))
        self.windowed = "width" in user_conf and "height" in user_conf
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

        self.window = WebRender(transparent=bool(user_conf.get("transparent", False)))

        # Set window properties
        if self.windowed:
            width = user_conf["width"]
            height = user_conf["height"]

            # Always use frameless window (no decorations)
            self.window.setWindowFlags(Qt.FramelessWindowHint)
            self.window.resize(width, height)

            # Calculate position
            if "x" in user_conf and "y" in user_conf:
                self.window_x = user_conf["x"]
                self.window_y = user_conf["y"]
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

        # Set up page refresh timer if configured
        if user_conf.get("refresh_interval", 0) > 0:
            self.refresh_timer = QTimer()
            self.refresh_timer.timeout.connect(self.window.browser.reload)
            self.refresh_timer.start(int(user_conf["refresh_interval"] * 1000))

    def show_window(self):
        if self.windowed:
            self.window.show()
            if self.window_x is not None and self.window_y is not None:
                self.window.move(self.window_x, self.window_y)
        else:
            self.window.showFullScreen()

        self.window.raise_()
        self.window.activateWindow()

        # Let cached web UIs update themselves after they are already visible.
        self.window.browser.page().runJavaScript(
            "window.dispatchEvent(new CustomEvent('fs42-guide-show'));"
        )

    def hide_window(self):
        self.window.hide()
        self.window.browser.page().runJavaScript(
            "window.dispatchEvent(new CustomEvent('fs42-guide-hide'));"
        )

    def shutdown_window(self):
        self.timer.stop()
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        self.window.close()
        if self.backdrop is not None:
            self.backdrop.close()
        self.quit()

    def tick(self):
        if self.queue and self.queue.qsize() > 0:
            msg = self.queue.get_nowait()
            print(f"WebRender received message: {msg}")
            # Persistent renderers stay alive between open/close operations so
            # QtWebEngine/Chromium only pays its startup cost once.
            if isinstance(msg, dict) and msg.get('type') == 'show_window':
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

            if msg == "show_window":
                self.show_window()
                return

            if msg == "hide_window":
                if self.persistent:
                    self.hide_window()
                else:
                    self.shutdown_window()
                return

            if msg == "shutdown_window":
                self.shutdown_window()
                return
            # Handle key injection commands
            if isinstance(msg, str) and msg.startswith("key:"):
                key_name = msg[4:]
                if key_name not in {"PageUp", "PageDown", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter"}:
                    print(f"WebRender: rejected disallowed key '{key_name}'")
                    return
                js = f"""
                document.dispatchEvent(new KeyboardEvent('keydown', {{
                    key: '{key_name}',
                    code: '{key_name}',
                    bubbles: true,
                    cancelable: true
                }}));
                """
                self.window.browser.page().runJavaScript(js)
                return

def web_render_runner(user_conf, queue):
    # Set up signal handler for web process - just exit cleanly
    def web_sigint_handler(sig, frame):
        print("WebRender process received SIGINT, exiting...")
        import sys
        sys.exit(0)

    signal.signal(signal.SIGINT, web_sigint_handler)

    # Set environment variables to enable autoplay
    import os
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--autoplay-policy=no-user-gesture-required --disable-web-security --allow-running-insecure-content --disable-features=VizDisplayCompositor'

    # Set graphics API before creating QApplication
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)

    app = WebRenderApp(user_conf, queue)

    # Navigate to URL after a short delay to ensure Qt is fully initialized
    def delayed_navigate():
        url = user_conf.get("web_url", "http://localhost:4242/static/diagnostics.html")
        if "url" in user_conf:
            app.window.navigate(user_conf["url"])
        else:
            app.window.navigate(url)

    QTimer.singleShot(100, delayed_navigate)

    app.exec()

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.getcwd())

    # Simple test config - customize as needed
    test_conf = {
        "url": "http://localhost:4242/static/diagnostics.html",
        "width": 800,
        "height": 600,
        # Uncomment to test specific positioning:
        # "x": 100,
        # "y": 100,
    }

    # Or load a station config by name
    # Uncomment and modify to use a station config:
    # from fs42.station_manager import StationManager
    # test_conf = StationManager().station_by_name("diagnostic")

    web_render_runner(test_conf, None)
