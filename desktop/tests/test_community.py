"""Community transport and local receipt tests; no actual HTTP requests."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import community
import core


POST_ID = "4ec7d00b-e91e-4aaf-b447-562e308c8e40"
OTHER_ID = "b9ad940c-76a5-4eea-925c-18911e55cbaa"
REQUEST_ID = "f316ca56-2f30-4fa5-8a44-07a2c7084e5c"
STAMP = "2026-09-24T12:00:00.000Z"


def public_bundle():
    settings = {"limit_total_0": 35}
    return {
        "schemaVersion": 1, "kind": "ghelper-profile-share", "author": "테스트",
        "profile": {"schemaVersion": 1, "name": "테스트 프리셋", "notes": "공개 메모",
                    "hardware": {"manufacturer": "ASUS", "model": "TEST", "cpu": "Test CPU",
                                 "gpu": ["Test GPU"], "ram_gb": 32, "bios": "000"},
                    "settings": settings, "settingsHash": core.digest(settings), "activeMode": 0,
                    "ghelperVersion": "test"},
        "runs": [{"totalScore": 12000, "graphicsScore": 13000, "cpuScore": 10000, "mode": 0,
                  "createdAt": STAMP, "noiseDbA": None, "fanRpm": None, "notes": "",
                  "settingsHash": core.digest(settings)}], "verification": "user-reported",
    }


def public_post():
    return {**public_bundle(), "id": POST_ID, "createdAt": STAMP}


class FakeResponse:
    def __init__(self, data=None, *, status=200, raw=None, headers=None):
        self.status = status
        self.raw = raw if raw is not None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(self.raw))}
        self.headers.update(headers or {})
        self.closed = False
        self.read_limits = []

    def read(self, maximum):
        self.read_limits.append(maximum)
        return self.raw[:maximum]

    def close(self):
        self.closed = True


class FakeLab:
    def __init__(self, data):
        self.data = Path(data)
        self.data.mkdir()
        self.lock = threading.RLock()
        self.bundle = public_bundle()
        self.imported = []

    def share_bundle(self, profile_id, run_ids, author):
        if not self.lock._is_owned():
            raise AssertionError("Public bundle capture must hold Lab.lock")
        return copy.deepcopy(self.bundle)

    def import_profile(self, profile):
        if not self.lock._is_owned():
            raise AssertionError("Local import must hold Lab.lock")
        # Delegate the material key/range gate to the actual core implementation.
        core.checked_settings(profile["settings"])
        self.imported.append(copy.deepcopy(profile))
        return {**profile, "id": "local-profile", "origin": "imported"}


class QueueTransport:
    def __init__(self, lab, *responses):
        self.lab = lab
        self.responses = list(responses)
        self.requests = []
        self.before_request = None

    def __call__(self, request, timeout):
        if self.lab.lock._is_owned():
            raise AssertionError("No network operation may hold Lab.lock")
        if timeout != 10:
            raise AssertionError("Network timeout must be 10 seconds")
        self.requests.append(request)
        if self.before_request:
            self.before_request(request)
        if not self.responses:
            raise AssertionError("Unexpected additional HTTP request")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lab = FakeLab(self.root / "data")
        self.receipt_path = self.lab.data / "community-owned.json"

    def service(self, *responses):
        transport = QueueTransport(self.lab, *responses)
        return community.CommunityService(self.lab, transport=transport), transport

    def success(self, replayed=False):
        return FakeResponse({"id": POST_ID, "createdAt": STAMP, "replayed": replayed}, status=200 if replayed else 201)

    def publish(self, service):
        return service.publish("local-profile-id", ["local-run-id"], "테스트", REQUEST_ID)

    def private_entry(self):
        return json.loads(self.receipt_path.read_text(encoding="utf-8"))["entries"][0]

    def test_only_fixed_https_origin_or_injected_loopback_is_allowed(self):
        transport = QueueTransport(self.lab)
        for address in ("http://ghelper.optiwork.co.kr", "https://evil.example", "https://ghelper.optiwork.co.kr/other",
                        "https://user:pass@ghelper.optiwork.co.kr", "https://ghelper.optiwork.co.kr?x=1",
                        "http://localhost:8080", "https://ghelper.optiwork.co.kr#fragment"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                # Loopback is rejected when no injected transport is supplied.
                community.CommunityService(self.lab, base_url=address)
        for address in ("http://127.0.0.1:8080", "http://[::1]:8080", "https://localhost:8080"):
            community.CommunityService(self.lab, base_url=address, transport=transport)
        self.assertEqual(transport.requests, [])

    def test_browse_encodes_query_and_returns_only_sanitized_fields(self):
        post = public_post()
        post["deleteToken"] = "private-response-extra"
        post["profile"]["sourceFile"] = "private-path"
        post["runs"][0]["sourceFile"] = "private-score-path"
        response = FakeResponse({"posts": [post], "nextCursor": "opaque+/="})
        service, transport = self.service(response)
        result = service.browse("TEST & more", "cursor+/=")
        query = parse_qs(urlsplit(transport.requests[0].full_url).query)
        self.assertEqual(query, {"limit": ["30"], "model": ["TEST & more"], "cursor": ["cursor+/="]})
        self.assertEqual(result["nextCursor"], "opaque+/=")
        self.assertNotIn("private-", json.dumps(result))
        self.assertTrue(response.closed)
        self.assertEqual(response.read_limits, [4 * 1024 * 1024 + 1])

    def test_invalid_uuid_is_rejected_before_any_request(self):
        service, transport = self.service()
        for value in ("../admin", "https://evil.example", "not-an-id", POST_ID.upper(), "0" * 32):
            with self.subTest(id=value), self.assertRaises(ValueError):
                service.detail(value)
        with self.assertRaises(ValueError):
            service.publish("p", [], "author", "not-a-request-id")
        self.assertEqual(transport.requests, [])

    def test_page_bounds_duplicate_ids_and_bad_cursor_are_rejected(self):
        cases = ({"posts": [public_post()] * 31, "nextCursor": None},
                 {"posts": [public_post(), public_post()], "nextCursor": None},
                 {"posts": {}, "nextCursor": None}, {"posts": [], "nextCursor": "\r\ninjection"})
        for payload in cases:
            service, _ = self.service(FakeResponse(payload))
            with self.subTest(payload_type=type(payload["posts"]).__name__), self.assertRaises(ValueError):
                service.browse()

    def test_detail_rejects_mismatched_post_id(self):
        post = public_post()
        post["id"] = OTHER_ID
        service, _ = self.service(FakeResponse({"post": post}))
        with self.assertRaises(ValueError):
            service.detail(POST_ID)

    def test_import_fetches_outside_lab_lock_then_uses_local_validation(self):
        service, _ = self.service(FakeResponse({"post": public_post()}))
        result = service.import_post(POST_ID)
        self.assertEqual(result["origin"], "imported")
        self.assertEqual(len(self.lab.imported), 1)

    def test_imported_malicious_hotkey_is_blocked_by_core(self):
        post = public_post()
        post["profile"]["settings"] = {"keybind_profile_0": 123}
        post["profile"]["settingsHash"] = core.digest(post["profile"]["settings"])
        post["runs"] = []
        service, _ = self.service(FakeResponse({"post": post}))
        with self.assertRaises(ValueError) as caught:
            service.import_post(POST_ID)
        self.assertNotIn("keybind_profile", str(caught.exception))
        self.assertEqual(self.lab.imported, [])

    def test_real_lab_import_rechecks_hash_without_modifying_config(self):
        # The complete Lab import gate, not only the fixture's allowlist gate.
        config_path = self.root / "config.json"
        config_path.write_text('{"performance_mode":0,"limit_total_0":35}', encoding="utf-8")
        with patch.object(core.bridge, "detect_hardware", return_value=public_bundle()["profile"]["hardware"]), \
             patch.object(core.bridge, "discover", return_value={"config_path": str(config_path), "config_verified": True}):
            lab = core.Lab(self.root / "real-lab", self.root / "assets")
        post = public_post()
        post["profile"]["settingsHash"] = "a" * 64
        post["runs"] = []
        transport = QueueTransport(lab, FakeResponse({"post": post}))
        service = community.CommunityService(lab, transport=transport)
        before = config_path.read_bytes()
        with self.assertRaises(ValueError):
            service.import_post(POST_ID)
        self.assertEqual(lab.db["profiles"], [])
        self.assertEqual(config_path.read_bytes(), before)

    def test_publish_saves_private_receipt_before_network_and_exposes_no_key(self):
        service, transport = self.service(self.success())
        pending = []
        transport.before_request = lambda _: pending.append(self.private_entry())
        result = self.publish(service)
        entry = self.private_entry()
        self.assertEqual(result, {"id": POST_ID, "createdAt": STAMP, "replayed": False})
        self.assertEqual(pending[0]["status"], "pending")
        self.assertIsNone(pending[0]["id"])
        self.assertRegex(entry["deleteToken"], r"^[0-9a-f]{64}$")
        self.assertEqual(entry["bundleHash"], hashlib.sha256(community._encode(entry["bundle"])).hexdigest())
        request = transport.requests[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["idempotency-key"], REQUEST_ID)
        self.assertEqual(headers["x-delete-token"], entry["deleteToken"])
        self.assertNotIn(entry["deleteToken"], request.data.decode())
        self.assertEqual(set(service.owned()[0]), {"requestId", "id", "createdAt", "name", "status"})
        self.assertNotIn(entry["deleteToken"], json.dumps(service.owned()))

    def test_lost_post_response_retries_identical_payload_and_token_after_restart(self):
        service, transport = self.service(TimeoutError("synthetic secret must not escape"))
        with self.assertRaises(ValueError) as caught:
            self.publish(service)
        self.assertNotIn("synthetic", str(caught.exception))
        first = transport.requests[0]
        self.assertEqual(service.owned()[0]["status"], "pending")
        service2, retry_transport = self.service(self.success(replayed=True))
        # Changed current content must not affect retry of the already-saved public bundle.
        self.lab.bundle["profile"]["notes"] = "changed later"
        result = service2.retry(REQUEST_ID)
        second = retry_transport.requests[0]
        self.assertTrue(result["replayed"])
        self.assertEqual(first.data, second.data)
        self.assertEqual(dict(first.header_items()), dict(second.header_items()))
        self.assertEqual(service2.owned()[0]["status"], "published")

    def test_reusing_request_id_with_changed_payload_is_rejected_without_network(self):
        service, transport = self.service(TimeoutError())
        with self.assertRaises(ValueError):
            self.publish(service)
        before = self.receipt_path.read_bytes()
        self.lab.bundle["profile"]["notes"] = "changed"
        with self.assertRaises(ValueError):
            self.publish(service)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(self.receipt_path.read_bytes(), before)

    def test_confirmed_request_replay_uses_receipt_without_another_post(self):
        service, transport = self.service(self.success())
        self.publish(service)
        self.assertTrue(self.publish(service)["replayed"])
        self.assertTrue(service.retry(REQUEST_ID)["replayed"])
        self.assertEqual(len(transport.requests), 1)

    def test_concurrent_service_instances_share_receipt_lock(self):
        service, transport = self.service(self.success())
        second = community.CommunityService(self.lab, transport=transport)
        barrier = threading.Barrier(2)

        def publish_together(client):
            barrier.wait(timeout=2)
            return self.publish(client)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(publish_together, client) for client in (service, second)]
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual({result["id"] for result in results}, {POST_ID})
        self.assertEqual(len(service.owned()), 1)

    def test_receipt_save_failure_prevents_first_post(self):
        service, transport = self.service()
        with patch.object(community.os, "replace", side_effect=OSError("private disk path")):
            with self.assertRaises(ValueError) as caught:
                self.publish(service)
        self.assertNotIn("private disk path", str(caught.exception))
        self.assertEqual(transport.requests, [])
        self.assertFalse(self.receipt_path.exists())

    def test_confirmation_save_failure_preserves_pending_receipt_for_retry(self):
        service, transport = self.service(self.success(), self.success(replayed=True))
        real_save = service._save_receipts
        count = 0

        def fail_second_save(entries):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError("합성 저장 실패")
            real_save(entries)

        with patch.object(service, "_save_receipts", side_effect=fail_second_save):
            with self.assertRaises(ValueError):
                self.publish(service)
        self.assertEqual(service.owned()[0]["status"], "pending")
        self.assertTrue(service.retry(REQUEST_ID)["replayed"])
        self.assertEqual(transport.requests[0].data, transport.requests[1].data)

    def test_deletion_failure_keeps_private_receipt_then_success_removes_it(self):
        error = HTTPError("fixed-url", 503, "secret-body", {}, io.BytesIO(b"private server details"))
        service, transport = self.service(self.success(), error, FakeResponse({"deleted": True}))
        self.publish(service)
        before = self.receipt_path.read_bytes()
        token = self.private_entry()["deleteToken"]
        with self.assertRaises(ValueError) as caught:
            service.delete_post(POST_ID)
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(self.receipt_path.read_bytes(), before)
        self.assertEqual(service.delete_post(POST_ID), {"id": POST_ID, "deleted": True})
        self.assertEqual(service.owned(), [])
        self.assertEqual(json.loads(transport.requests[-1].data), {"deleteToken": token})
        self.assertEqual(transport.requests[-1].method, "DELETE")

    def test_delete_unknown_post_and_retry_unknown_request_never_send_network(self):
        service, transport = self.service()
        with self.assertRaises(ValueError):
            service.delete_post(POST_ID)
        with self.assertRaises(ValueError):
            service.retry(REQUEST_ID)
        self.assertEqual(transport.requests, [])

    def test_delete_requires_explicit_success_body_before_local_removal(self):
        service, _ = self.service(self.success(), FakeResponse({"deleted": False}))
        self.publish(service)
        before = self.receipt_path.read_bytes()
        with self.assertRaises(ValueError):
            service.delete_post(POST_ID)
        self.assertEqual(self.receipt_path.read_bytes(), before)

    def test_corrupt_or_tampered_receipt_is_preserved_and_never_sent(self):
        service, transport = self.service(TimeoutError())
        with self.assertRaises(ValueError):
            self.publish(service)
        data = json.loads(self.receipt_path.read_text(encoding="utf-8"))
        data["entries"][0]["bundle"]["unexpectedPrivateField"] = "should-never-upload"
        self.receipt_path.write_text(json.dumps(data), encoding="utf-8")
        before = self.receipt_path.read_bytes()
        with self.assertRaises(ValueError):
            service.retry(REQUEST_ID)
        self.assertEqual(self.receipt_path.read_bytes(), before)
        self.assertEqual(len(transport.requests), 1)

    def test_strict_json_rejects_duplicates_nonfinite_malformed_and_wrong_media(self):
        cases = [FakeResponse(raw=b'{"posts":[],"posts":[],"nextCursor":null}'),
                 FakeResponse(raw=b'{"posts":[],"nextCursor":NaN}'), FakeResponse(raw=b'not-json'),
                 FakeResponse(raw=b'[]'), FakeResponse(raw=b'\xff'),
                 FakeResponse({"posts": [], "nextCursor": None}, headers={"Content-Type": "text/html"})]
        for response in cases:
            service, _ = self.service(response)
            with self.subTest(raw=response.raw[:20]), self.assertRaises(ValueError):
                service.browse()
            self.assertTrue(response.closed)

    def test_response_limits_cover_declared_and_undeclared_size(self):
        declared = FakeResponse({"posts": []}, headers={"Content-Length": str(4 * 1024 * 1024 + 1)})
        undeclared = FakeResponse(raw=b" " * (4 * 1024 * 1024 + 1))
        undeclared.headers.pop("Content-Length")
        truncated = FakeResponse({"posts": []}, headers={"Content-Length": "999"})
        for response in (declared, undeclared, truncated):
            service, _ = self.service(response)
            with self.assertRaises(ValueError):
                service.browse()
            self.assertTrue(response.closed)
        self.assertEqual(declared.read_limits, [])
        self.assertEqual(undeclared.read_limits, [4 * 1024 * 1024 + 1])

    def test_redirects_are_denied_and_no_second_request_is_followed(self):
        service, transport = self.service(FakeResponse({}, status=302, headers={"Location": "https://evil.example"}))
        with self.assertRaises(ValueError):
            service.browse()
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNone(community._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_http_error_does_not_expose_body_url_or_delete_token(self):
        error = HTTPError("https://secret.example/private", 409, "do-not-show-token", {}, io.BytesIO(b"secret response"))
        service, _ = self.service(error)
        with self.assertRaises(ValueError) as caught:
            self.publish(service)
        for forbidden in ("secret", "do-not-show-token", self.private_entry()["deleteToken"]):
            self.assertNotIn(forbidden, str(caught.exception))
        self.assertEqual(service.owned()[0]["status"], "pending")

    def test_network_is_refused_when_integrator_holds_lab_lock(self):
        service, transport = self.service()
        with self.lab.lock, self.assertRaises(ValueError):
            service.browse()
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
