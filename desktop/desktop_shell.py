"""Windows tray and embedded WebView2 shell. No tuning actions live here."""
import threading
from pathlib import Path

TITLE = 'GHelper Profile Lab'
BUSY_MESSAGE = '벤치마크를 중단하고 원래 모드로 복원한 뒤 종료하세요.'


class DesktopShell:
    def __init__(self, lab, server, closing, assets, data, instance):
        self.lab, self.server, self.closing = lab, server, closing
        self.assets, self.data, self.instance = Path(assets), Path(data), instance
        self.window = self.tray = None
        self._stopped = threading.Event()
        self._finish_lock = threading.Lock()
        self._watcher = None

    def show(self, *_):
        if not self.closing.is_set() and self.window:
            self.window.restore()
            self.window.show()

    def hide(self, *_):
        if self.window and not self.closing.is_set():
            self.window.hide()

    def on_closing(self):
        if self.closing.is_set():
            return True
        self.hide()
        return False

    def request_exit(self, *_):
        with self.lab.lock:
            if self.lab.active():
                if self.tray:
                    self.tray.notify(BUSY_MESSAGE, TITLE)
                self.show()
                return False
            if self.closing.is_set():
                return True
            self.closing.set()
        # A tray callback must not join its own message loop.
        threading.Thread(target=self.finish_exit, daemon=True).start()
        return True

    def finish_exit(self):
        with self._finish_lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
            if self.tray:
                self.tray.stop()
            self.server.shutdown()
            if self.window:
                self.window.destroy()

    def _watch_instance(self):
        while not self._stopped.is_set():
            if self.instance.wait_for_show(500) and not self._stopped.is_set():
                self.show()

    def _ready(self):
        # pywebview's callback starts on a worker after the native window exists.
        self.tray.run_detached()
        self._watcher = threading.Thread(target=self._watch_instance, daemon=True)
        self._watcher.start()

    def run(self, url, show=False):
        import ctypes
        import webview
        import pystray
        from PIL import Image

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GHelperProfileLab.Desktop')
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
        self.window = webview.create_window(
            TITLE, url, width=940, height=740, min_size=(740, 580),
            hidden=not show, background_color='#0e141a', text_select=True,
        )
        self.window.events.closing += self.on_closing
        self.window.events.minimized += self.hide
        self.tray = pystray.Icon(
            'GHelperProfileLab', Image.open(self.assets / 'app.ico'), TITLE,
            menu=pystray.Menu(
                pystray.MenuItem('Profile Lab 열기', self.show, default=True),
                pystray.MenuItem('트레이로 숨기기', self.hide),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('종료', self.request_exit),
            ),
        )
        try:
            webview.start(
                self._ready, gui='edgechromium', debug=False,
                storage_path=str(self.data / 'WebView2'), private_mode=True,
                icon=str(self.assets / 'app.ico'),
            )
        finally:
            self._stopped.set()
            if self.tray:
                self.tray.stop()
            if self._watcher:
                self._watcher.join(timeout=2)

