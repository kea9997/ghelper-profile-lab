"""Fixed-origin public community client with private, durable deletion receipts.

No network request holds Lab.lock. Only public share bundles leave this process.
Tests may inject transport(request, timeout=10), returning a response object with
status, headers, read(limit), and close(); production never permits redirects.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

DEFAULT_URL = "https://ghelper.optiwork.co.kr"
_TIMEOUT = 10
_MAX_RESPONSE = 4 * 1024 * 1024
_MAX_REQUEST = 128 * 1024
_MAX_JOURNAL = 64 * 1024 * 1024
_MAX_RECEIPTS = 500
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_LOCKS_GUARD = threading.Lock()
_RECEIPT_LOCKS: dict[str, threading.RLock] = {}


def _invalid():
    return ValueError("공유 자료실 응답 형식이 올바르지 않습니다.")


def _uuid(value) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError("자료 또는 요청 ID 형식이 올바르지 않습니다.")
    return str(uuid.UUID(value))


def _text(value, limit: int, *, required=False) -> str:
    if (not isinstance(value, str) or len(value) > limit or
            any((ord(c) < 32 and c not in "\n\r\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise _invalid()
    if required and not value.strip():
        raise _invalid()
    return value


def _timestamp(value) -> str:
    value = _text(value, 64, required=True)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise _invalid() from None
    return value


def _hash(value) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise _invalid()
    return value


def _number(value, minimum, maximum, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
        raise _invalid()
    return value


def _strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _invalid()
            result[key] = value
        return result

    def reject_constant(_):
        raise _invalid()

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None


def _encode(value) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _invalid() from None


def _profile(value) -> dict:
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise _invalid()
    hardware = value.get("hardware")
    if not isinstance(hardware, dict):
        raise _invalid()
    gpu = hardware.get("gpu")
    if not isinstance(gpu, list) or len(gpu) > 6:
        raise _invalid()
    safe_hardware = {k: _text(hardware.get(k, ""), 200) for k in ("manufacturer", "model", "cpu", "bios")}
    safe_hardware["gpu"] = [_text(g, 200) for g in gpu]
    safe_hardware["ram_gb"] = _number(hardware.get("ram_gb"), 0.01, 2048, nullable=True)
    settings = value.get("settings")
    if not isinstance(settings, dict) or not 1 <= len(settings) <= 120:
        raise _invalid()
    for key, setting in settings.items():
        _text(key, 80, required=True)
        if type(setting) is not int and not isinstance(setting, str):
            raise _invalid()
        if isinstance(setting, str):
            _text(setting, 200)
        elif abs(setting) > 1_000_000:
            raise _invalid()
    mode = value.get("activeMode")
    if mode is not None and (type(mode) is not int or mode not in (0, 1, 2)):
        raise _invalid()
    # Unsupported tuning keys and exact setting ranges are authoritatively
    # checked by Lab.import_profile before creating any local profile.
    return {
        "schemaVersion": 1, "name": _text(value.get("name"), 80),
        "notes": _text(value.get("notes", ""), 2000), "hardware": safe_hardware,
        "ghelperVersion": _text(value.get("ghelperVersion", "unknown"), 80),
        "settings": dict(settings), "settingsHash": _hash(value.get("settingsHash")), "activeMode": mode,
    }


def _run(value) -> dict:
    if not isinstance(value, dict):
        raise _invalid()
    result = {}
    for key in ("totalScore", "graphicsScore", "cpuScore"):
        score = value.get(key)
        if type(score) is not int or not 1 <= score <= 1_000_000:
            raise _invalid()
        result[key] = score
    mode = value.get("mode")
    if type(mode) is not int or mode not in (0, 1, 2):
        raise _invalid()
    result.update({
        "mode": mode, "createdAt": _timestamp(value.get("createdAt")),
        "noiseDbA": _number(value.get("noiseDbA"), 0, 140, nullable=True),
        "fanRpm": _number(value.get("fanRpm"), 0, 20000, nullable=True),
        "notes": _text(value.get("notes", ""), 2000), "settingsHash": _hash(value.get("settingsHash")),
    })
    return result


def _bundle(value) -> dict:
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise _invalid()
    if value.get("kind") != "ghelper-profile-share" or value.get("verification") != "user-reported":
        raise _invalid()
    runs = value.get("runs")
    if not isinstance(runs, list) or len(runs) > 20:
        raise _invalid()
    profile = _profile(value.get("profile"))
    runs = [_run(run) for run in runs]
    if any(run["settingsHash"] != profile["settingsHash"] for run in runs):
        raise _invalid()
    result = {"schemaVersion": 1, "kind": "ghelper-profile-share", "author": _text(value.get("author"), 40),
              "profile": profile, "runs": runs, "verification": "user-reported"}
    if len(_encode(result)) > _MAX_REQUEST:
        raise ValueError("공유 자료의 크기가 128 KiB 제한을 초과했습니다.")
    return result


def _post(value) -> dict:
    if not isinstance(value, dict):
        raise _invalid()
    return {**_bundle(value), "id": _uuid(value.get("id")), "createdAt": _timestamp(value.get("createdAt"))}


def _cursor(value):
    if value is None:
        return None
    value = _text(value, 2048, required=True)
    if not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise _invalid()
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_error(status):
    messages = {
        400: "공유 요청 내용을 확인하세요.", 403: "공유 자료실에서 요청을 허용하지 않았습니다.",
        404: "자료가 없거나 이 컴퓨터의 삭제 권한으로 확인할 수 없습니다.",
        409: "같은 요청 ID에 다른 내용 또는 삭제키가 등록되어 있습니다.",
        410: "이미 삭제된 게시 요청입니다. 새 요청으로 게시하세요.",
        413: "공유 자료의 크기가 서버 제한을 초과했습니다.", 415: "공유 요청 형식을 처리할 수 없습니다.",
        429: "게시 요청이 많습니다. 잠시 후 같은 요청을 다시 시도하세요.",
        503: "공유 자료실이 잠시 응답하지 않습니다. 나중에 다시 시도하세요.",
    }
    if 300 <= status < 400:
        return ValueError("공유 자료실의 주소 이동 요청을 거부했습니다.")
    return ValueError(messages.get(status, "공유 자료실 요청을 완료하지 못했습니다. 나중에 다시 시도하세요."))


class CommunityService:
    def __init__(self, lab, base_url=DEFAULT_URL, transport=None):
        if not isinstance(base_url, str):
            raise ValueError("공유 자료실 주소가 올바르지 않습니다.")
        base_url = base_url.rstrip("/")
        try:
            parsed = urlsplit(base_url)
            _ = parsed.port  # Reject malformed or out-of-range ports.
        except ValueError:
            raise ValueError("공유 자료실 주소가 올바르지 않습니다.") from None
        testing_loopback = transport is not None and parsed.hostname in {"127.0.0.1", "::1", "localhost"} and parsed.scheme in {"http", "https"}
        if (base_url != DEFAULT_URL and not testing_loopback) or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("지정된 HTTPS 공유 자료실만 사용할 수 있습니다.")
        self.lab = lab
        self.base_url = base_url
        self._transport = transport or build_opener(_NoRedirect()).open
        self._journal = Path(lab.data) / "community-owned.json"
        lock_key = os.path.normcase(str(self._journal.resolve()))
        with _LOCKS_GUARD:
            self._receipt_lock = _RECEIPT_LOCKS.setdefault(lock_key, threading.RLock())

    def _request(self, method, path, *, payload=None, headers=None):
        owns_lab_lock = getattr(self.lab.lock, "_is_owned", None)
        if callable(owns_lab_lock) and owns_lab_lock():
            raise ValueError("다른 로컬 작업의 잠금을 해제한 뒤 공유 요청을 다시 시도하세요.")
        body = _encode(payload) if payload is not None else None
        if body is not None and len(body) > _MAX_REQUEST:
            raise ValueError("공유 요청의 크기가 128 KiB 제한을 초과했습니다.")
        request_headers = {"Accept": "application/json", "User-Agent": "GHelperProfileLab/1"}
        if body is not None:
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        request_headers.update(headers or {})
        request = Request(self.base_url + path, data=body, headers=request_headers, method=method)
        try:
            with closing(self._transport(request, timeout=_TIMEOUT)) as response:
                status = response.status
                allowed = {200, 201} if method == "POST" else {200, 204} if method == "DELETE" else {200}
                if type(status) is not int or status not in allowed:
                    raise _http_error(status if type(status) is int else 500)
                length = response.headers.get("Content-Length")
                if length is not None:
                    try:
                        size = int(length)
                    except (TypeError, ValueError):
                        raise _invalid() from None
                    if not 0 <= size <= _MAX_RESPONSE:
                        raise ValueError("공유 자료실 응답이 크기 제한을 초과했습니다.")
                raw = response.read(_MAX_RESPONSE + 1)
                if not isinstance(raw, bytes) or len(raw) > _MAX_RESPONSE:
                    raise ValueError("공유 자료실 응답이 크기 제한을 초과했습니다.")
                if length is not None and len(raw) != size:
                    raise _invalid()
                if status == 204 and method == "DELETE" and not raw:
                    return {"deleted": True}
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise _invalid()
                result = _strict_json(raw)
                if not isinstance(result, dict):
                    raise _invalid()
                return result
        except HTTPError as exc:
            try:
                exc.close()
            finally:
                raise _http_error(exc.code) from None
        except (URLError, OSError, TimeoutError, http.client.HTTPException):
            raise ValueError("공유 자료실에 연결하지 못했습니다. 연결을 확인하고 같은 요청을 다시 시도하세요.") from None

    def browse(self, model="", cursor=None, query=""):
        model = _text(model, 200)
        if any(ord(c) < 32 for c in model):
            raise ValueError("모델 검색어 형식이 올바르지 않습니다.")
        query_text = _text(query, 160)
        if any(ord(c) < 32 for c in query_text):
            raise ValueError("기기 사양 검색어 형식이 올바르지 않습니다.")
        cursor = _cursor(cursor)
        parameters = {"limit": 30}
        if model:
            parameters["model"] = model
        if query_text:
            parameters["q"] = query_text
        if cursor is not None:
            parameters["cursor"] = cursor
        response = self._request("GET", "/api/profiles?" + urlencode(parameters))
        posts = response.get("posts")
        if not isinstance(posts, list) or len(posts) > 30:
            raise _invalid()
        posts = [_post(post) for post in posts]
        if len({post["id"] for post in posts}) != len(posts):
            raise _invalid()
        return {"posts": posts, "nextCursor": _cursor(response.get("nextCursor"))}

    def detail(self, id):
        id = _uuid(id)
        response = self._request("GET", "/api/profiles/" + id)
        post = _post(response.get("post"))
        if post["id"] != id:
            raise _invalid()
        return {"post": post}

    def import_post(self, id):
        profile = self.detail(id)["post"]["profile"]
        with self.lab.lock:
            try:
                return self.lab.import_profile(profile)
            except (ValueError, TypeError, KeyError):
                raise ValueError("공유 프리셋의 설정 검증에 실패했습니다. 이 자료를 가져올 수 없습니다.") from None

    def _load_receipts(self):
        if not self._journal.exists():
            return []
        try:
            if self._journal.stat().st_size > _MAX_JOURNAL:
                raise _invalid()
            with self._journal.open("rb") as stream:
                raw = stream.read(_MAX_JOURNAL + 1)
            if len(raw) > _MAX_JOURNAL:
                raise _invalid()
            data = _strict_json(raw)
            if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1:
                raise _invalid()
            entries = data.get("entries")
            if not isinstance(entries, list) or len(entries) > _MAX_RECEIPTS:
                raise _invalid()
            requests, ids = set(), set()
            for item in entries:
                if not isinstance(item, dict):
                    raise _invalid()
                request_id = _uuid(item.get("requestId"))
                if request_id in requests:
                    raise _invalid()
                requests.add(request_id)
                _hash(item.get("deleteToken"))
                _hash(item.get("bundleHash"))
                _timestamp(item.get("createdAt"))
                _text(item.get("name"), 80)
                bundle = _bundle(item.get("bundle"))
                if (_encode(bundle) != _encode(item["bundle"]) or
                        hashlib.sha256(_encode(bundle)).hexdigest() != item["bundleHash"] or
                        item["name"] != bundle["profile"]["name"]):
                    raise _invalid()
                if item.get("status") == "published":
                    id = _uuid(item.get("id"))
                    if id in ids:
                        raise _invalid()
                    ids.add(id)
                elif item.get("status") != "pending" or item.get("id") is not None:
                    raise _invalid()
            return entries
        except (OSError, ValueError, TypeError, KeyError):
            raise ValueError("내 게시 기록을 읽을 수 없습니다. community-owned.json을 보존하고 복구 후 다시 시도하세요.") from None

    def _save_receipts(self, entries):
        payload = _encode({"schemaVersion": 1, "entries": entries})
        if len(payload) > _MAX_JOURNAL or len(entries) > _MAX_RECEIPTS:
            raise ValueError("내 게시 기록의 저장 한도를 초과했습니다.")
        temporary = None
        try:
            self._journal.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=".community-", suffix=".tmp", dir=self._journal.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._journal)
        except OSError:
            raise ValueError("내 게시 기록을 저장하지 못했습니다. 저장 공간과 파일 권한을 확인하세요.") from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def owned(self):
        with self._receipt_lock:
            entries = self._load_receipts()
            return [{key: item.get(key) for key in ("requestId", "id", "createdAt", "name", "status")}
                    for item in reversed(entries)]

    def _send_pending(self, entries, entry):
        if entry["status"] == "published":
            return {"id": entry["id"], "createdAt": entry["createdAt"], "replayed": True}
        response = self._request("POST", "/api/profiles", payload=entry["bundle"],
                                 headers={"Idempotency-Key": entry["requestId"], "X-Delete-Token": entry["deleteToken"]})
        id = _uuid(response.get("id"))
        created_at = _timestamp(response.get("createdAt"))
        replayed = response.get("replayed", False)
        if type(replayed) is not bool or any(item is not entry and item.get("id") == id for item in entries):
            raise _invalid()
        entry.update({"id": id, "createdAt": created_at, "status": "published"})
        self._save_receipts(entries)
        return {"id": id, "createdAt": created_at, "replayed": replayed}

    def publish(self, profile_id, run_ids, author, request_id):
        request_id = _uuid(request_id)
        with self.lab.lock:
            try:
                bundle = _bundle(self.lab.share_bundle(profile_id, run_ids, author))
            except (ValueError, TypeError, KeyError):
                raise ValueError("공유할 프리셋과 연결된 정상 결과, 작성자 정보를 확인하세요.") from None
        bundle_hash = hashlib.sha256(_encode(bundle)).hexdigest()
        with self._receipt_lock:
            entries = self._load_receipts()
            entry = next((item for item in entries if item["requestId"] == request_id), None)
            if entry is not None:
                if entry["bundleHash"] != bundle_hash:
                    raise ValueError("같은 요청 ID의 게시 내용이 바뀌었습니다. 기존 요청을 재시도하거나 새 요청 ID를 사용하세요.")
            else:
                entry = {"requestId": request_id, "deleteToken": secrets.token_hex(32), "bundleHash": bundle_hash,
                         "bundle": bundle, "id": None, "createdAt": datetime.now(timezone.utc).isoformat(),
                         "name": bundle["profile"]["name"], "status": "pending"}
                entries.append(entry)
                # Persist the exact payload and deletion capability before POST;
                # if the reply is lost, retry cannot orphan a successfully saved post.
                self._save_receipts(entries)
            return self._send_pending(entries, entry)

    def retry(self, request_id):
        request_id = _uuid(request_id)
        with self._receipt_lock:
            entries = self._load_receipts()
            entry = next((item for item in entries if item["requestId"] == request_id), None)
            if entry is None:
                raise ValueError("이 컴퓨터에 저장된 게시 요청을 찾을 수 없습니다.")
            return self._send_pending(entries, entry)

    def delete_post(self, id):
        id = _uuid(id)
        with self._receipt_lock:
            entries = self._load_receipts()
            entry = next((item for item in entries if item.get("id") == id and item["status"] == "published"), None)
            if entry is None:
                raise ValueError("이 컴퓨터에 삭제 권한이 저장된 게시글만 삭제할 수 있습니다.")
            response = self._request("DELETE", "/api/profiles/" + id, payload={"deleteToken": entry["deleteToken"]})
            if response.get("deleted") is not True:
                raise _invalid()
            self._save_receipts([item for item in entries if item is not entry])
            return {"id": id, "deleted": True}
