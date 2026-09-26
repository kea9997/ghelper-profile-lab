"""Loopback HTTP routing tests with a fake community, never a remote service."""
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

import app


TOKEN = "synthetic-local-session-token-for-tests"
POST_ID = "4ec7d00b-e91e-4aaf-b447-562e308c8e40"
REQUEST_ID = "f316ca56-2f30-4fa5-8a44-07a2c7084e5c"


class FakeLab:
    def __init__(self):
        self.lock = threading.RLock()

    def active(self):
        return False

    def share_bundle(self, profile_id, run_ids, author, mode_profile_ids=None):
        if not self.lock._is_owned():
            raise AssertionError("Local prepare must preserve the Lab lock")
        result = {"profileId": profile_id, "runIds": run_ids, "author": author}
        if mode_profile_ids is not None: result['modeProfileIds']=mode_profile_ids
        return result


class FakeCommunity:
    def __init__(self, lab):
        self.lab = lab
        self.calls = []
        self.fail_method = None

    def invoke(self, method, args, result):
        if self.lab.lock._is_owned():
            raise AssertionError("Community route held Lab.lock during possible network IO")
        self.calls.append((method, args))
        if self.fail_method == method:
            raise ValueError("합성 자료실 오류")
        return result

    def browse(self, model, cursor, query=""):
        args = (model, cursor, query) if query else (model, cursor)
        return self.invoke("browse", args, {"posts": [{"id": POST_ID}], "nextCursor": "next-page"})

    def detail(self, id):
        return self.invoke("detail", (id,), {"post": {"id": id}})

    def owned(self):
        return self.invoke("owned", (), [{"requestId": REQUEST_ID, "id": POST_ID, "status": "published"}])

    def import_post(self, id):
        return self.invoke("import_post", (id,), {"id": "new-local-profile", "origin": "imported"})

    def publish(self, profile_id, run_ids, author, request_id, mode_profile_ids=None):
        args = (profile_id, run_ids, author, request_id)
        if mode_profile_ids is not None: args += (mode_profile_ids,)
        return self.invoke("publish", args, {"id": POST_ID, "createdAt": "test-time"})

    def retry(self, request_id):
        return self.invoke("retry", (request_id,), {"id": POST_ID, "replayed": True})

    def delete_post(self, id):
        return self.invoke("delete_post", (id,), {"id": id, "deleted": True})


class HttpCommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.assets = Path(self.temp.name)
        web = self.assets / "web"
        web.mkdir()
        self.fragments = {
            "__APP_STYLE__": ("style.css", "/* synthetic app style */"),
            "__SETTINGS_STYLE__": ("settings-view.css", "/* synthetic settings style */"),
            "__SETTINGS_JS__": ("settings-view.js", "/* synthetic settings script */"),
            "__SHARE_SELECTION_JS__": ("share-selection.js", "/* synthetic three mode selection */"),
            "__APP_JS__": ("app.js", 'const syntheticSession="__SESSION_TOKEN__";'),
            "__LIBRARY_JS__": ("library.js", "/* synthetic community script */"),
        }
        (web / "index.html").write_text("<html><head>__APP_STYLE____SETTINGS_STYLE__</head>"
                                         "<body>__SETTINGS_JS____SHARE_SELECTION_JS____APP_JS____LIBRARY_JS__"
                                         "<span>__SESSION_TOKEN__</span></body></html>", encoding="utf-8")
        for filename, fragment in self.fragments.values():
            (web / filename).write_text(fragment, encoding="utf-8")
        self.lab = FakeLab()
        self.community = FakeCommunity(self.lab)
        self.closing = threading.Event()
        self.server = app.create_server(self.lab, self.assets, TOKEN, closing=self.closing, community=self.community)
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.assertFalse(self.worker.is_alive())

    def request(self, method, path, body=None, headers=None):
        request_headers = {"Host": "127.0.0.1:" + str(self.server.server_port),
                           "X-Session-Token": TOKEN, "Origin": self.base, "Connection": "close"}
        request_headers.update(headers or {})
        payload = b""
        if body is not None:
            payload = json.dumps(body).encode()
            request_headers.setdefault("Content-Type", "application/json; charset=utf-8")
            request_headers["Content-Length"] = str(len(payload))
        request_head = "\r\n".join([f"{method} {path} HTTP/1.1"] +
                                     [f"{key}: {value}" for key, value in request_headers.items()]) + "\r\n\r\n"
        # Send one complete wire request. HTTPConnection sends headers and body
        # separately; an early authentication rejection can close the socket
        # between those writes on Windows, before the test reads the real 403.
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=3) as connection:
            connection.sendall(request_head.encode("ascii") + payload)
            with http.client.HTTPResponse(connection) as response:
                response.begin()
                data = response.read(1024 * 1024)
                return response.status, dict(response.getheaders()), data

    def test_get_browse_detail_and_owned_forward_arguments_outside_lab_lock(self):
        status, _, raw = self.request("GET", "/api/community/browse?model=TEST%20%26%20model&cursor=page%2B%2F%3D")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["nextCursor"], "next-page")
        self.assertEqual(self.community.calls[-1], ("browse", ("TEST & model", "page+/=")))
        status, _, raw = self.request("GET", "/api/community/post?id=" + POST_ID)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"post": {"id": POST_ID}})
        status, _, raw = self.request("GET", "/api/community/owned")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"posts": [{"requestId": REQUEST_ID, "id": POST_ID, "status": "published"}]})
        self.assertEqual([call[0] for call in self.community.calls], ["browse", "detail", "owned"])

    def test_post_publish_import_retry_delete_forward_arguments_outside_lab_lock(self):
        payload = {"profileId": "local-profile", "runIds": ["run-one"], "author": "작성자", "requestId": REQUEST_ID}
        status, _, raw = self.request("POST", "/api/community/publish", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["id"], POST_ID)
        self.assertEqual(self.community.calls[-1], ("publish", ("local-profile", ["run-one"], "작성자", REQUEST_ID)))
        for route, body, expected_method, expected_args in (
            ("import", {"id": POST_ID}, "import_post", (POST_ID,)),
            ("retry", {"requestId": REQUEST_ID}, "retry", (REQUEST_ID,)),
            ("delete", {"id": POST_ID}, "delete_post", (POST_ID,)),
        ):
            with self.subTest(route=route):
                status, _, _ = self.request("POST", "/api/community/" + route, body)
                self.assertEqual(status, 200)
                self.assertEqual(self.community.calls[-1], (expected_method, expected_args))

    def test_template_inlines_all_fragments_and_session_without_placeholders(self):
        status, headers, raw = self.request("GET", "/?session=" + TOKEN)
        self.assertEqual(status, 200)
        html = raw.decode("utf-8")
        for marker, (_, fragment) in self.fragments.items():
            self.assertNotIn(marker, html)
            self.assertIn(fragment.replace("__SESSION_TOKEN__", TOKEN), html)
        self.assertNotRegex(html, r"__[A-Z_]+__")
        self.assertEqual(html.count(TOKEN), 2)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])

    def test_api_token_host_and_origin_failures_never_reach_community(self):
        bad_headers = [
            {"X-Session-Token": "wrong-token"}, {"X-Session-Token": ""},
            {"Host": "evil.example"}, {"Host": "localhost:" + str(self.server.server_port)},
            {"Origin": "https://evil.example"}, {"Origin": "null"},
        ]
        for headers in bad_headers:
            for method, path, body in (("GET", "/api/community/owned", None),
                                       ("POST", "/api/community/delete", {"id": POST_ID})):
                with self.subTest(method=method, headers=headers):
                    status, _, raw = self.request(method, path, body, headers=headers)
                    self.assertEqual(status, 403)
                    self.assertIn("error", json.loads(raw))
        self.assertEqual(self.community.calls, [])

    def test_template_rejects_invalid_session_or_host(self):
        for path, headers in (("/", {}), ("/?session=wrong", {}), ("/?session=" + TOKEN, {"Host": "evil.example"})):
            with self.subTest(path=path, headers=headers):
                status, _, raw = self.request("GET", path, headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn(TOKEN.encode(), raw)
                self.assertNotIn(b"synthetic app style", raw)

    def test_closing_blocks_remote_mutations_before_community_call(self):
        self.closing.set()
        for route, body in (("publish", {"profileId": "p", "requestId": REQUEST_ID}),
                            ("import", {"id": POST_ID}), ("retry", {"requestId": REQUEST_ID}),
                            ("delete", {"id": POST_ID})):
            with self.subTest(route=route):
                status, _, raw = self.request("POST", "/api/community/" + route, body)
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(raw))
        self.assertEqual(self.community.calls, [])

    def test_community_errors_unknown_routes_and_missing_payload_are_http_errors(self):
        self.community.fail_method = "browse"
        status, _, raw = self.request("GET", "/api/community/browse")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw), {"error": "합성 자료실 오류"})
        self.community.fail_method = "retry"
        status, _, raw = self.request("POST", "/api/community/retry", {"requestId": REQUEST_ID})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw), {"error": "합성 자료실 오류"})
        for method, path, body, expected in (("GET", "/api/community/missing", None, 404),
                                              ("POST", "/api/community/missing", {}, 404),
                                              ("POST", "/api/community/publish", {}, 400)):
            with self.subTest(path=path, method=method):
                status, _, raw = self.request(method, path, body)
                self.assertEqual(status, expected)
                self.assertIn("error", json.loads(raw))

    def test_three_mode_selection_is_forwarded_to_prepare_and_publish(self):
        mapping={'2':'quiet-settings','0':'balanced-settings','1':'turbo-settings'}
        body={'profileId':'base','runIds':['quiet','balanced','turbo'],'author':'User','modeProfileIds':mapping}
        status,_,raw=self.request('POST','/api/community/prepare',body)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['modeProfileIds'],mapping)
        self.assertEqual(self.community.calls,[])
        status,_,_=self.request('POST','/api/community/publish',{**body,'requestId':REQUEST_ID})
        self.assertEqual(status,200)
        self.assertEqual(self.community.calls,[('publish',('base',['quiet','balanced','turbo'],'User',REQUEST_ID,mapping))])

    def test_local_prepare_keeps_its_lab_lock_and_does_not_invoke_remote_service(self):
        payload = {"profileId": "local-profile", "runIds": ["run-one"], "author": "작성자"}
        status, _, raw = self.request("POST", "/api/community/prepare", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), payload)
        self.assertEqual(self.community.calls, [])


if __name__ == "__main__":
    unittest.main()
