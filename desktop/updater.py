"""Verified, opt-in updates from this project's public GitHub releases."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


APP_VERSION = '0.4.4'
REPOSITORY = 'kea9997/ghelper-profile-lab'
RELEASE_API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASE_PAGE = f'https://github.com/{REPOSITORY}/releases/latest'
ASSET_NAME = 'GHelperProfileLab.exe'
MAX_DOWNLOAD = 100 * 1024 * 1024
VERSION_RE = re.compile(r'^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
HASH_RE = re.compile(r'^sha256:([0-9a-fA-F]{64})$')


def version_tuple(value):
    match = VERSION_RE.fullmatch(value) if isinstance(value, str) and len(value) <= 40 else None
    if not match or any(len(part) > 9 for part in match.groups()):
        raise ValueError('릴리스 버전 형식이 올바르지 않습니다.')
    return tuple(int(part) for part in match.groups())


def release_info(payload):
    if not isinstance(payload, dict) or payload.get('draft') or payload.get('prerelease'):
        raise ValueError('최신 정식 릴리스 정보를 확인할 수 없습니다.')
    tag = payload.get('tag_name', '')
    version = version_tuple(tag)
    if not tag.startswith('v'):
        raise ValueError('릴리스 태그 형식이 올바르지 않습니다.')
    assets = payload.get('assets')
    if not isinstance(assets, list):
        raise ValueError('릴리스 파일 목록을 확인할 수 없습니다.')
    asset = next((item for item in assets if isinstance(item, dict) and item.get('name') == ASSET_NAME), None)
    if not asset:
        raise ValueError('Windows 실행 파일이 릴리스에 없습니다.')
    expected_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{ASSET_NAME}'
    digest = asset.get('digest')
    match = HASH_RE.fullmatch(digest) if isinstance(digest, str) else None
    size = asset.get('size')
    if (asset.get('browser_download_url') != expected_url or asset.get('state') != 'uploaded'
            or not match or type(size) is not int or not 0 < size <= MAX_DOWNLOAD):
        raise ValueError('릴리스 파일의 주소·크기·SHA-256 정보를 확인할 수 없습니다.')
    return {
        'currentVersion': APP_VERSION,
        'latestVersion': '.'.join(str(part) for part in version),
        'available': version > version_tuple(APP_VERSION),
        'releaseUrl': f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
        'notes': str(payload.get('body') or '')[:4000],
        'downloadUrl': expected_url,
        'sha256': match.group(1).lower(),
        'size': size,
    }


def check_latest(opener=urllib.request.urlopen):
    request = urllib.request.Request(
        RELEASE_API,
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': f'GHelperProfileLab/{APP_VERSION}'},
    )
    try:
        with opener(request, timeout=12) as response:
            raw = response.read(512 * 1024 + 1)
    except OSError as exc:
        raise ValueError('GitHub 릴리스를 확인하지 못했습니다. 인터넷 연결을 확인해 주세요.') from exc
    if len(raw) > 512 * 1024:
        raise ValueError('릴리스 정보가 너무 큽니다.')
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ValueError('GitHub 릴리스 응답을 읽지 못했습니다.') from exc
    return release_info(payload)


def public_info(info):
    return {key: info[key] for key in ('currentVersion', 'latestVersion', 'available', 'releaseUrl', 'notes', 'size')}


def download_verified(info, data_dir, opener=urllib.request.urlopen):
    """Stage an executable only after its size and release digest match."""
    target_dir = Path(data_dir) / 'updates' / (info['latestVersion'] + '-' + uuid.uuid4().hex)
    target_dir.mkdir(parents=True, exist_ok=False)
    partial = target_dir / (ASSET_NAME + '.part')
    staged = target_dir / ASSET_NAME
    request = urllib.request.Request(info['downloadUrl'], headers={'User-Agent': f'GHelperProfileLab/{APP_VERSION}'})
    sha = hashlib.sha256()
    size = 0
    try:
        with opener(request, timeout=20) as response, partial.open('xb') as output:
            started = time.monotonic()
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD or time.monotonic() - started > 180:
                    raise ValueError('업데이트 다운로드 제한을 초과했습니다.')
                output.write(chunk)
                sha.update(chunk)
        if size != info['size'] or sha.hexdigest() != info['sha256']:
            raise ValueError('다운로드한 실행 파일의 크기 또는 SHA-256이 일치하지 않습니다.')
        with partial.open('rb') as source:
            if source.read(2) != b'MZ':
                raise ValueError('다운로드한 파일이 Windows 실행 파일이 아닙니다.')
        os.replace(partial, staged)
        return staged
    except Exception:
        partial.unlink(missing_ok=True)
        staged.unlink(missing_ok=True)
        target_dir.rmdir()
        raise


def _ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def updater_script(executable, staged, status_file, parent_pid, launch_args=''):
    """Run after the app exits; restore the previous EXE if replacement fails."""
    target = _ps_string(executable)
    incoming = _ps_string(staged)
    status = _ps_string(status_file)
    backup = _ps_string(str(executable) + '.backup-' + uuid.uuid4().hex)
    args = _ps_string(launch_args)
    return f"""
$ErrorActionPreference = 'Stop'
$target = {target}
$incoming = {incoming}
$status = {status}
$backup = {backup}
$launchArgs = {args}
try {{ Wait-Process -Id {int(parent_pid)} -Timeout 90 -ErrorAction SilentlyContinue }} catch {{}}
$installed = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {{
    try {{
        [System.IO.File]::Move($target, $backup)
        try {{ [System.IO.File]::Move($incoming, $target) }}
        catch {{ [System.IO.File]::Move($backup, $target); throw }}
        $installed = $true
        break
    }} catch {{ Start-Sleep -Milliseconds 500 }}
}}
if ($installed) {{
    try {{
        if ($launchArgs) {{ Start-Process -FilePath $target -ArgumentList $launchArgs -WindowStyle Hidden }}
        else {{ Start-Process -FilePath $target -WindowStyle Hidden }}
        [System.IO.File]::WriteAllText($status, 'updated')
        try {{ [System.IO.File]::Delete($backup) }} catch {{}}
    }} catch {{
        try {{
            [System.IO.File]::Delete($target)
            [System.IO.File]::Move($backup, $target)
            if ($launchArgs) {{ Start-Process -FilePath $target -ArgumentList $launchArgs -WindowStyle Hidden }}
            else {{ Start-Process -FilePath $target -WindowStyle Hidden }}
        }} catch {{}}
        [System.IO.File]::WriteAllText($status, 'failed')
    }}
}} else {{
    [System.IO.File]::WriteAllText($status, 'failed')
    if ([System.IO.File]::Exists($target)) {{
        try {{
            if ($launchArgs) {{ Start-Process -FilePath $target -ArgumentList $launchArgs -WindowStyle Hidden }}
            else {{ Start-Process -FilePath $target -WindowStyle Hidden }}
        }} catch {{}}
    }}
}}
"""


def launch_installer(staged, data_dir, executable=None, popen=subprocess.Popen):
    if os.name != 'nt' or not getattr(sys, 'frozen', False):
        raise ValueError('앱의 Windows 실행 파일에서만 자동 설치할 수 있습니다.')
    executable = Path(executable or sys.executable).resolve()
    if executable.name.lower() != ASSET_NAME.lower():
        raise ValueError('공식 GHelperProfileLab.exe에서 업데이트해 주세요.')
    # Check directory write access before shutting down the running app.
    try:
        with tempfile.NamedTemporaryFile(dir=executable.parent):
            pass
    except OSError as exc:
        raise ValueError('현재 실행 폴더에 쓰기 권한이 없습니다. GitHub 릴리스에서 직접 설치해 주세요.') from exc
    status_file = Path(data_dir) / 'update-status.txt'
    status_file.unlink(missing_ok=True)
    system_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    powershell = system_root / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    if not powershell.is_file():
        raise ValueError('Windows PowerShell을 찾지 못했습니다. GitHub 릴리스에서 직접 설치해 주세요.')
    # Keep the replacement on the same volume as the running portable EXE.
    incoming = executable.parent / ('.GHelperProfileLab-update-' + uuid.uuid4().hex + '.exe')
    try:
        with Path(staged).open('rb') as source, incoming.open('xb') as output:
            shutil.copyfileobj(source, output, 1024 * 1024)
        if hashlib.sha256(incoming.read_bytes()).digest() != hashlib.sha256(Path(staged).read_bytes()).digest():
            raise ValueError('업데이트 파일 복사 검증에 실패했습니다.')
    except Exception:
        incoming.unlink(missing_ok=True)
        raise
    script = updater_script(executable, incoming, status_file, os.getpid(), subprocess.list2cmdline(sys.argv[1:]))
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    try:
        popen([str(powershell), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
               '-EncodedCommand', encoded], close_fds=True,
              creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    except Exception:
        incoming.unlink(missing_ok=True)
        raise
    try:
        Path(staged).unlink(missing_ok=True)
        Path(staged).parent.rmdir()
    except OSError:
        pass


class UpdateService:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def check(self):
        return public_info(check_latest())

    def install(self):
        info = check_latest()
        if not info['available']:
            raise ValueError('이미 최신 버전입니다.')
        try:
            staged = download_verified(info, self.data_dir)
        except OSError as exc:
            raise ValueError('업데이트 파일을 받지 못했습니다. 인터넷 연결과 저장 공간을 확인해 주세요.') from exc
        try:
            launch_installer(staged, self.data_dir)
        except Exception as exc:
            staged.unlink(missing_ok=True)
            try: staged.parent.rmdir()
            except OSError: pass
            if isinstance(exc, ValueError): raise
            raise ValueError('자동 설치를 시작하지 못했습니다. GitHub 릴리스에서 직접 설치해 주세요.') from exc
        return {'message': f"v{info['latestVersion']} 설치를 준비했습니다. 앱을 다시 시작합니다."}
