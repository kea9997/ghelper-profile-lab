"""Bounded Windows discovery and explicitly requested desktop actions.

Discovery is read-only. This module never writes G-Helper configuration, kills a
process, changes a license, or invokes a benchmark engine directly.
G-Helper semantics: seerge/g-helper app/AppConfig.cs and InputDispatcher.cs.
3DMark CLI: https://support.benchmarks.ul.com/support/solutions/articles/44002145411
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_DEFAULT_KEYS = {0: 0x80, 1: 0x81, 2: 0x7F}  # F17, F18, F16
_MAX_CONFIG_BYTES = 2 * 1024 * 1024
_ENGINE_NAME = re.compile(r"^3dmarktimespy(?:extreme|ext)?(?:64)?\.exe$", re.I)


def _powershell_json(script: str, timeout: float = 20):
    if os.name != "nt":
        raise RuntimeError("이 기능은 Windows에서만 사용할 수 있습니다.")
    prefix = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", prefix + script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False, creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode:
        # Do not surface raw shell output containing private local paths.
        raise RuntimeError("Windows 시스템 정보를 읽지 못했습니다.")
    try:
        return json.loads(result.stdout.lstrip("\ufeff").strip() or "null")
    except ValueError as exc:
        raise RuntimeError("Windows 시스템 정보 응답을 해석하지 못했습니다.") from exc


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _as_list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def detect_hardware() -> dict:
    """Read product descriptions only, never serial numbers or machine IDs."""
    data = _powershell_json(r"""
        $system = Get-CimInstance Win32_ComputerSystem -Property Manufacturer,Model,TotalPhysicalMemory;
        $cpu = @(Get-CimInstance Win32_Processor -Property Name | Select-Object -ExpandProperty Name);
        $gpu = @(Get-CimInstance Win32_VideoController -Property Name,PNPDeviceID | Select-Object Name,@{n='Physical';e={$_.PNPDeviceID -like 'PCI\*'}});
        $bios = Get-CimInstance Win32_BIOS -Property SMBIOSBIOSVersion;
        $ram = (Get-CimInstance Win32_PhysicalMemory -Property Capacity | Measure-Object -Property Capacity -Sum).Sum;
        @{manufacturer=$system.Manufacturer;model=$system.Model;cpu=$cpu;gpu=$gpu;
          ram_bytes=$(if($ram){$ram}else{$system.TotalPhysicalMemory});bios=$bios.SMBIOSBIOSVersion} | ConvertTo-Json -Depth 4 -Compress
    """) or {}
    gpu = []
    virtual = re.compile(r"virtual|remote|indirect|displaylink|parsec|spacedesk|mirage|dummy|basic render|citrix|vmware|hyper-v", re.I)
    for row in _as_list(data.get("gpu")):
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or "").strip()
        if name and row.get("Physical") is True and not virtual.search(name) and name not in gpu:
            gpu.append(name)
    memory = data.get("ram_bytes")
    try:
        ram_gb = round(float(memory) / (1024 ** 3), 1) if memory else None
    except (TypeError, ValueError):
        ram_gb = None
    return {
        "manufacturer": str(data.get("manufacturer") or "").strip(),
        "model": str(data.get("model") or "").strip(),
        "cpu": " / ".join(dict.fromkeys(str(x).strip() for x in _as_list(data.get("cpu")) if x)),
        "gpu": gpu, "ram_gb": ram_gb,
        "bios": str(data.get("bios") or "").strip(),
    }


def _installation_snapshot() -> dict:
    """Inspect named processes, named tasks and known registry locations only."""
    return _powershell_json(r"""
        $processes = @(Get-CimInstance Win32_Process -Filter "Name='GHelper.exe' OR Name='G-Helper.exe'" -Property Name,ExecutablePath |
            Select-Object Name,ExecutablePath);
        $taskExe = @();
        try { $taskExe = @(Get-ScheduledTask -TaskName '*GHelper*' -ErrorAction Stop |
            ForEach-Object { $_.Actions } | Select-Object -ExpandProperty Execute) } catch {}
        $install = @();
        foreach ($root in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
                            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')) {
            if (Test-Path -LiteralPath $root) {
                $install += @(Get-ItemProperty -Path ($root + '\*') -ErrorAction SilentlyContinue |
                    Where-Object { $_.DisplayName -match '^3DMark(?:\s|$)' } |
                    Select-Object -ExpandProperty InstallLocation -ErrorAction SilentlyContinue)
            }
        }
        $steam = @();
        foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
            if (Test-Path -LiteralPath $key) {
                $entry = Get-ItemProperty -LiteralPath $key;
                if ($entry.SteamPath) { $steam += $entry.SteamPath }
                if ($entry.InstallPath) { $steam += $entry.InstallPath }
            }
        }
        @{processes=$processes;task_exes=$taskExe;install_roots=$install;steam_roots=$steam;
          documents=[Environment]::GetFolderPath('MyDocuments')} | ConvertTo-Json -Depth 4 -Compress
    """) or {}


def _unique_paths(paths):
    result, seen = [], set()
    for value in paths:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            continue
        path = Path(os.path.expandvars(str(value).strip().strip('"')))
        if not path.is_absolute():
            continue
        key = os.path.normcase(str(path))
        if key not in seen:
            result.append(path)
            seen.add(key)
    return result


def _read_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file() or p.stat().st_size > _MAX_CONFIG_BYTES:
        raise ValueError("G-Helper 설정 파일을 읽을 수 없거나 크기 제한을 초과했습니다.")
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not data:
        raise ValueError("G-Helper 설정은 비어 있지 않은 JSON 객체여야 합니다.")
    return data


def _valid_config(path: Path) -> bool:
    try:
        data = _read_config(path)
        mode = data.get("performance_mode")
        return type(mode) is int and 0 <= mode <= 4
    except (OSError, ValueError, UnicodeError):
        return False


def _log_evidence(log_paths: list[Path]) -> list[Path]:
    """Use latest log first and latest load within it; cap all file reads."""
    available = []
    for path in log_paths:
        try:
            if path.is_file():
                available.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    result = []
    for _, path in sorted(available, reverse=True):
        try:
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 512 * 1024))
                text = stream.read(512 * 1024).decode("utf-8-sig", errors="replace")
            matches = re.findall(r"Config loaded from ([^\r\n]+)", text)
            if matches:
                # The most recent load may be a .bak: do not silently fall back
                # to an earlier successful load in that same session.
                result.extend(_unique_paths([matches[-1]]))
        except OSError:
            continue
    return result


def _steam_libraries(steam_roots: list[Path]) -> list[Path]:
    libraries = list(steam_roots)
    for root in steam_roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            if vdf.is_file() and vdf.stat().st_size <= 512 * 1024:
                text = vdf.read_text(encoding="utf-8-sig", errors="replace")
                paths = re.findall(r'"path"\s+"((?:\\.|[^"\\])*)"', text)
                libraries.extend(_unique_paths([p.replace("\\\\", "\\") for p in paths]))
        except OSError:
            continue
    return _unique_paths(libraries)


def _find_benchmarks(snapshot: dict) -> tuple[str | None, str | None]:
    roots = list(_as_list(snapshot.get("install_roots")))
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base:
            roots.extend([str(Path(base) / "UL" / "3DMark"), str(Path(base) / "Futuremark" / "3DMark")])
    steam_roots = _unique_paths(_as_list(snapshot.get("steam_roots")))
    roots.extend(str(p / "steamapps" / "common" / "3DMark") for p in _steam_libraries(steam_roots))
    ui, cli = None, None
    for root in _unique_paths(roots):
        # Fixed installation layouts only; no recursive disk search.
        for folder in (root, root / "bin" / "x64", root / "bin" / "x86"):
            if not ui:
                for name in ("3DMark.exe", "3DMarkLauncher.exe"):
                    candidate = folder / name
                    if candidate.is_file():
                        ui = str(candidate)
                        break
            candidate = folder / "3DMarkCmd.exe"
            if not cli and candidate.is_file():
                cli = str(candidate)
    return ui, cli


def _file_version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        version = _powershell_json("(Get-Item -LiteralPath " + _ps_literal(path) + ").VersionInfo.FileVersion | ConvertTo-Json -Compress")
        return str(version) if version else None
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return None


def discover() -> dict:
    snapshot = _installation_snapshot()
    processes = _as_list(snapshot.get("processes"))
    process_exes = _unique_paths([p.get("ExecutablePath") for p in processes if isinstance(p, dict)])
    task_exes = _unique_paths(_as_list(snapshot.get("task_exes")))
    exe_paths = [p for p in process_exes + task_exes if p.is_file() and p.name.lower() in {"ghelper.exe", "g-helper.exe"}]
    ghelper_exe = str(exe_paths[0]) if exe_paths else None
    config_roots = [Path(os.environ[name]) / "GHelper" for name in ("APPDATA", "PROGRAMDATA") if os.environ.get(name)]
    evidence = _log_evidence([p / "log.txt" for p in config_roots])
    portable = [p.parent / "config.json" for p in exe_paths]
    candidates = [p for p in _unique_paths(evidence + portable + [p / "config.json" for p in config_roots]) if p.is_file()]
    verified = None
    reason = "active_config_unverified"
    if evidence:
        newest = evidence[0]
        if newest.name.lower() == "config.json" and _valid_config(newest):
            verified, reason = newest, "latest_ghelper_log"
    elif process_exes:
        # A scheduled task's executable is only a candidate. A running process's
        # adjacent config has precedence in upstream AppConfig initialization.
        for p in process_exes:
            candidate = p.parent / "config.json"
            if _valid_config(candidate):
                verified, reason = candidate, "running_executable_portable_config"
                break
    selected = verified or next((p for p in candidates if p.name.lower() == "config.json" and _valid_config(p)), None)
    benchmark, cli = _find_benchmarks(snapshot)
    documents = snapshot.get("documents") or str(Path.home() / "Documents")
    warnings = []
    if processes and not process_exes:
        warnings.append("G-Helper는 실행 중이지만 실행 경로를 읽을 수 없습니다. 관리자 권한 차이일 수 있습니다.")
    if not verified:
        warnings.append("현재 G-Helper 설정 경로를 검증하지 못했습니다. 설정 파일을 직접 선택하세요.")
    if cli:
        warnings.append("3DMark CLI 파일을 찾았습니다. 라이선스 유효 여부는 실행 시 3DMark가 확인합니다.")
    return {
        "config_path": str(selected) if selected else None,
        "config_candidates": [str(p) for p in candidates],
        "config_verified": verified is not None, "config_source": reason,
        "ghelper_running": bool(processes), "ghelper_exe": ghelper_exe,
        "ghelper_version": _file_version(ghelper_exe),
        "benchmark_exe": benchmark, "cli_exe": cli,
        "results_dir": str(Path(documents) / "3DMark"), "warnings": warnings,
    }


# Explicit Windows widths: ctypes.c_ulong is 64-bit on some development hosts.
_DWORD = ctypes.c_uint32
_WORD = ctypes.c_uint16
_ULONG_PTR = ctypes.c_size_t


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", _DWORD), ("cntUsage", _DWORD), ("th32ProcessID", _DWORD),
                ("th32DefaultHeapID", _ULONG_PTR), ("th32ModuleID", _DWORD),
                ("cntThreads", _DWORD), ("th32ParentProcessID", _DWORD),
                ("pcPriClassBase", ctypes.c_int32), ("dwFlags", _DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def _running_names() -> list[str]:
    if os.name != "nt":
        raise RuntimeError("Windows 프로세스 목록이 필요합니다.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [_DWORD, _DWORD]
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = ctypes.c_int
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.CreateToolhelp32Snapshot(0x2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise RuntimeError("프로세스 목록을 확인할 수 없어 작업을 중단했습니다.")
    try:
        item = _PROCESSENTRY32W()
        item.dwSize = ctypes.sizeof(item)
        if not kernel.Process32FirstW(handle, ctypes.byref(item)):
            raise RuntimeError("프로세스 목록을 확인할 수 없어 작업을 중단했습니다.")
        names = [item.szExeFile]
        while kernel.Process32NextW(handle, ctypes.byref(item)):
            names.append(item.szExeFile)
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise RuntimeError("프로세스 목록 조회가 끝나지 않아 작업을 중단했습니다.")
        return names
    finally:
        kernel.CloseHandle(handle)


def ghelper_running() -> bool:
    return any(name.lower() in {"ghelper.exe", "g-helper.exe"} for name in _running_names())


def get_benchmark_running() -> bool:
    """The UI/launcher staying open is not a running Time Spy workload."""
    return any(_ENGINE_NAME.fullmatch(name) for name in _running_names())


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", _DWORD), ("BatteryFullLifeTime", _DWORD)]


def ac_connected() -> bool | None:
    if os.name != "nt":
        return None
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetSystemPowerStatus.argtypes = [ctypes.POINTER(_SYSTEM_POWER_STATUS)]
        kernel.GetSystemPowerStatus.restype = ctypes.c_int
        status = _SYSTEM_POWER_STATUS()
        if not kernel.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        return {0: False, 1: True}.get(status.ACLineStatus)
    except (OSError, AttributeError):
        return None


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", _WORD), ("wScan", _WORD), ("dwFlags", _DWORD),
                ("time", _DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32), ("mouseData", _DWORD),
                ("dwFlags", _DWORD), ("time", _DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", _DWORD), ("wParamL", _WORD), ("wParamH", _WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", _DWORD), ("data", _INPUTUNION)]


def _configured_chord(config: dict, mode: int) -> tuple[int, list[int]]:
    if str(config.get("skip_hotkeys", 0)) == "1":
        raise RuntimeError("G-Helper의 단축키가 비활성화되어 있습니다 (skip_hotkeys).")
    key = config.get(f"keybind_profile_{mode}", _DEFAULT_KEYS[mode])
    if type(key) is not int or not 0x70 <= key <= 0x87:
        raise RuntimeError("안전한 모드 전환을 위해 모드 단축키는 F1–F24여야 합니다.")
    modifier = config.get("modifier_keybind_alt", "")
    if not isinstance(modifier, str):
        raise RuntimeError("G-Helper 보조 단축키의 수정키 설정이 잘못되었습니다.")
    tokens = modifier.lower().split("-") if modifier.strip() else ["shift", "control", "alt"]
    # Upstream supports other combinations, but only the documented default is
    # dispatched here to avoid triggering Windows/system keyboard shortcuts.
    if set(tokens) != {"shift", "control", "alt"} or len(tokens) != 3:
        raise RuntimeError("자동 전환은 기본 수정키 조합 Shift-Control-Alt만 지원합니다.")
    # Duplicate profile hotkeys would apply multiple modes in InputDispatcher.
    for other, default in {0: 0x80, 1: 0x81, 2: 0x7F, 3: 0x82, 4: 0x83}.items():
        if other != mode and config.get(f"keybind_profile_{other}", default) == key:
            raise RuntimeError("모드 단축키가 다른 프로필과 중복됩니다.")
    collisions = {0x7C, 0x7D, 0x7E, 0x70, 0x71, 0x72, 0x73, 0x75, 0x76, 0x77, 0x78}
    other_keys = [config.get("keybind_profile", 0x74), config.get("keybind_xgm", 0x84), config.get("keybind_overlay", 0x4F)]
    if any(type(other_key) is not int for other_key in other_keys):
        raise RuntimeError("다른 G-Helper 단축키 설정을 검증하지 못했습니다.")
    collisions.update(other_keys)
    if key in collisions:
        raise RuntimeError("모드 단축키가 다른 G-Helper 동작과 충돌할 수 있습니다.")
    return key, [0x11, 0x10, 0x12]  # Control, Shift, Alt


def _send_hotkey(key: int, modifiers: list[int]) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows에서만 단축키를 보낼 수 있습니다.")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(_INPUT), ctypes.c_int]
    user.SendInput.restype = ctypes.c_uint32
    user.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user.GetAsyncKeyState.restype = ctypes.c_int16
    if any(user.GetAsyncKeyState(vk) & 0x8000 for vk in [0x10, 0x11, 0x12, 0x5B, 0x5C, key]):
        raise RuntimeError("키보드의 수정키와 모드 단축키에서 손을 떼고 다시 시작하세요.")
    sequence = [(vk, 0) for vk in modifiers] + [(key, 0), (key, 2)] + [(vk, 2) for vk in reversed(modifiers)]
    events = (_INPUT * len(sequence))()
    for event, (vk, flags) in zip(events, sequence):
        event.type = 1
        event.ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
    sent = user.SendInput(len(events), events, ctypes.sizeof(_INPUT))
    if sent != len(events):
        # Release only our chord keys after a partial dispatch. Never retry the
        # action itself: an elevated G-Helper may reject lower-integrity input.
        releases = (_INPUT * (len(modifiers) + 1))()
        for event, vk in zip(releases, [key] + list(reversed(modifiers))):
            event.type = 1
            event.ki = _KEYBDINPUT(vk, 0, 2, 0, 0)
        user.SendInput(len(releases), releases, ctypes.sizeof(_INPUT))
        raise RuntimeError("단축키 전달에 실패했습니다. G-Helper와 앱의 권한 수준을 확인하세요.")


def switch_mode(mode: int, config_path: str, timeout: float = 12) -> None:
    if type(mode) is not int or mode not in _DEFAULT_KEYS:
        raise ValueError("성능 모드는 0, 1, 2만 지원합니다.")
    if timeout <= 0 or timeout > 120:
        raise ValueError("모드 확인 시간은 0초 초과 120초 이하여야 합니다.")
    if not ghelper_running():
        raise RuntimeError("모드 전환을 위해 G-Helper를 먼저 실행하세요.")
    state = discover()
    if (not state.get("config_verified") or not state.get("config_path") or
            os.path.normcase(os.path.abspath(config_path)) != os.path.normcase(os.path.abspath(state["config_path"]))):
        raise RuntimeError("실행 중인 G-Helper의 설정 경로를 검증하지 못해 모드를 전환하지 않았습니다.")
    config = _read_config(config_path)
    key, modifiers = _configured_chord(config, mode)
    if type(config.get("performance_mode")) is int and config["performance_mode"] == mode:
        return
    _send_hotkey(key, modifiers)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            readback = _read_config(config_path).get("performance_mode")
            if type(readback) is int and readback == mode:
                if not ghelper_running():
                    raise RuntimeError("모드 확인 도중 G-Helper가 종료되었습니다.")
                return
        except (OSError, ValueError, UnicodeError):
            pass  # Atomic config replacement can momentarily overlap a read.
        time.sleep(0.2)
    raise RuntimeError("설정 파일에서 모드 변경을 확인하지 못했습니다. G-Helper 상태와 권한 수준을 확인하세요.")


def start_benchmark(driver: str, discovery: dict, output_path: str) -> subprocess.Popen | None:
    if driver not in {"guided", "enterprise"}:
        raise ValueError("지원하지 않는 벤치마크 실행 방식입니다.")
    if get_benchmark_running():
        raise RuntimeError("Time Spy가 실행 중입니다. 완료 후 다시 시작하세요.")
    key = "benchmark_exe" if driver == "guided" else "cli_exe"
    raw = discovery.get(key)
    if not isinstance(raw, str) or not raw:
        raise RuntimeError("3DMark 실행 파일을 찾지 못했습니다.")
    executable = Path(raw)
    allowed = {"3dmark.exe", "3dmarklauncher.exe"} if driver == "guided" else {"3dmarkcmd.exe"}
    if not executable.is_absolute() or not executable.is_file() or executable.name.lower() not in allowed:
        raise RuntimeError("검증된 3DMark 실행 파일이 필요합니다.")
    if driver == "guided":
        subprocess.Popen([str(executable)], cwd=str(executable.parent), creationflags=CREATE_NO_WINDOW)
        return None
    output = Path(output_path)
    if not output.is_absolute() or output.suffix.lower() != ".3dmark-result" or not output.parent.is_dir() or output.exists():
        raise ValueError("새 결과 파일의 절대 경로와 .3dmark-result 확장자가 필요합니다.")
    definition_dirs = [executable.parent, executable.parent.parent, executable.parent.parent.parent]
    definition_dir = next((p for p in definition_dirs if (p / "timespy.3dmdef").is_file()), None)
    if definition_dir is None:
        raise RuntimeError("공식 timespy.3dmdef 파일을 찾지 못했습니다. 3DMark CLI 설치를 확인하세요.")
    return subprocess.Popen(
        [str(executable), "--definition=timespy.3dmdef", "--out=" + str(output)],
        cwd=str(definition_dir), creationflags=CREATE_NO_WINDOW,
    )
