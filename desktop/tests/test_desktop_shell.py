"""Desktop lifetime tests use mock native UI and a fake lab on loopback only."""
import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, call

from app import create_server
from desktop_shell import BUSY_MESSAGE, DesktopShell, TITLE


class FakeLab:
    def __init__(self):
        self.lock = threading.RLock()
        self.running = False
        self.start = Mock(return_value={"message": "started"})

    def active(self):
        return self.running

    def state(self):
        return {"running": self.running}


class DesktopShellTests(unittest.TestCase):
    def setUp(self):
        self.lab = FakeLab()
        self.closing = threading.Event()
        self.server = Mock(spec=["shutdown"])
        self.shell = DesktopShell(
            self.lab, self.server, self.closing, Path("assets"), Path("data"),
            Mock(spec=["wait_for_show"]),
        )
        self.shell.window = Mock(spec=["restore", "show", "hide", "destroy"])
        self.shell.tray = Mock(spec=["notify", "stop"])

    def test_window_close_hides_without_stopping_application(self):
        self.assertIs(self.shell.on_closing(), False)

        self.shell.window.hide.assert_called_once_with()
        self.shell.window.destroy.assert_not_called()
        self.shell.tray.stop.assert_not_called()
        self.server.shutdown.assert_not_called()
        self.assertFalse(self.closing.is_set())

    def test_window_close_is_allowed_during_exit(self):
        self.closing.set()

        self.assertIs(self.shell.on_closing(), True)
        self.shell.window.hide.assert_not_called()

    def test_busy_tray_exit_preserves_application_and_brings_window_back(self):
        self.lab.running = True

        self.assertIs(self.shell.request_exit(), False)

        self.assertFalse(self.closing.is_set())
        self.shell.tray.notify.assert_called_once_with(BUSY_MESSAGE, TITLE)
        self.assertEqual(self.shell.window.mock_calls, [call.restore(), call.show()])
        self.shell.tray.stop.assert_not_called()
        self.server.shutdown.assert_not_called()

    def test_show_restores_before_showing_window(self):
        self.shell.show()

        self.assertEqual(self.shell.window.mock_calls, [call.restore(), call.show()])

    def test_show_cannot_reopen_window_during_shutdown(self):
        self.closing.set()

        self.shell.show()

        self.assertEqual(self.shell.window.mock_calls, [])

    def test_finish_exit_is_idempotent(self):
        self.closing.set()

        self.shell.finish_exit()
        self.shell.finish_exit()

        self.shell.tray.stop.assert_called_once_with()
        self.server.shutdown.assert_called_once_with()
        self.shell.window.destroy.assert_called_once_with()


class ServerLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.lab = FakeLab()
        self.closing = threading.Event()
        self.shutdown_called = threading.Event()
        self.shutdown_callback = Mock(side_effect=self.shutdown_called.set)
        self.token = "test-desktop-lifetime-capability"
        self.server = create_server(
            self.lab, Path(__file__).resolve().parent.parent, self.token,
            closing=self.closing, on_shutdown=self.shutdown_callback,
        )
        self.worker = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": .01},
            daemon=True,
        )
        self.worker.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.worker.join(timeout=2)
        self.server.server_close()
        self.assertFalse(self.worker.is_alive(), "HTTP server did not stop")

    def request(self, method, path, body=None, token=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=2,
        )
        headers = {"X-Session-Token": self.token if token is None else token}
        encoded = None
        if body is not None:
            encoded = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_active_shutdown_is_rejected_and_server_stays_usable(self):
        self.lab.running = True

        status, payload = self.request("POST", "/api/shutdown", {})

        self.assertEqual(status, 400)
        self.assertIn("error", payload)
        self.assertFalse(self.closing.is_set())
        self.shutdown_callback.assert_not_called()
        self.assertEqual(
            self.request("GET", "/api/state"), (200, {"running": True}),
        )
        self.assertTrue(self.worker.is_alive())

    def test_shutdown_flag_prevents_a_new_benchmark(self):
        self.closing.set()

        status, payload = self.request(
            "POST", "/api/benchmark/start", {"driver": "guided", "cooldownSeconds": 0},
        )

        self.assertEqual(status, 400)
        self.assertIn("error", payload)
        self.lab.start.assert_not_called()
        self.assertTrue(self.closing.is_set())

    def test_authenticated_idle_shutdown_calls_host_callback(self):
        status, payload = self.request("POST", "/api/shutdown", {})

        self.assertEqual(status, 200)
        self.assertIn("message", payload)
        self.assertTrue(self.closing.is_set())
        self.assertTrue(self.shutdown_called.wait(timeout=2), "Host callback was not called")
        self.shutdown_callback.assert_called_once_with()

    def test_unauthenticated_shutdown_does_not_close_the_app(self):
        status, payload = self.request("POST", "/api/shutdown", {}, token="wrong-token")

        self.assertEqual(status, 403)
        self.assertIn("error", payload)
        self.assertFalse(self.closing.is_set())
        self.shutdown_callback.assert_not_called()
        self.assertEqual(
            self.request("GET", "/api/state"), (200, {"running": False}),
        )


if __name__ == "__main__":
    unittest.main()
