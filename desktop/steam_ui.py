"""Start the installed Time Spy preset through the normal 3DMark Steam UI.

3DMark Advanced/Steam does not license 3DMarkCmd. We drive only its visible
frontend and verify the selected preset before pressing its Run control.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import time


_DETAIL_ROUTE = "#TEST_DETAILS/TIME_SPY_PERFORMANCE"
_BENCHMARK_ROUTE = "#BENCHMARKS"


def _route(document) -> str:
    pattern = document.GetValuePattern()
    return pattern.Value if pattern else ""


def _process_path(pid: int) -> str:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, 0, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(buffer))
        return buffer.value if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else ""
    finally:
        kernel.CloseHandle(handle)


def _find_window(auto, executable: Path):
    expected = os.path.normcase(os.path.abspath(executable))
    matches = [window for window in auto.GetRootControl().GetChildren()
               if window.ControlTypeName == "WindowControl" and window.Name == "3DMark"
               and os.path.normcase(_process_path(window.ProcessId)) == expected]
    if len(matches) > 1:
        raise RuntimeError("3DMark 창이 여러 개라 실행할 창을 구분할 수 없습니다.")
    return matches[0] if matches else None


def _document(window):
    doc = window.DocumentControl(searchDepth=5)
    if not doc.Exists(0):
        raise RuntimeError("3DMark 화면을 읽을 수 없습니다. 창을 열어 둔 뒤 다시 시도하세요.")
    return doc


def _match_card(screenshot, template):
    """Return physical screen offset and confidence for the installed card art."""
    import cv2
    import numpy as np

    screen = cv2.cvtColor(np.asarray(screenshot.convert("RGB")), cv2.COLOR_RGB2GRAY)
    art = cv2.cvtColor(np.asarray(template.convert("RGB")), cv2.COLOR_RGB2GRAY)
    best = None
    for scale in (0.6, 0.7, 0.75, 0.85, 0.95, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0):
        resized = cv2.resize(art, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        height, width = resized.shape
        # The tile may cover/crop the art; exclude the ribbon and tile edges.
        inset = resized[int(height * .15):int(height * .85), int(width * .15):int(width * .85)]
        if min(inset.shape) < 25 or inset.shape[0] > screen.shape[0] or inset.shape[1] > screen.shape[1]:
            continue
        _, score, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(screen, inset, cv2.TM_CCOEFF_NORMED))
        candidate = (float(score), x + inset.shape[1] // 2, y + inset.shape[0] // 2)
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best


def _select_card(auto, window, template_path: Path, deadline: float):
    from PIL import Image, ImageGrab

    if not template_path.is_file():
        raise RuntimeError("Time Spy 화면 리소스를 찾을 수 없습니다. 3DMark 설치를 확인하세요.")
    template = Image.open(template_path)
    for _ in range(9):
        if time.monotonic() >= deadline:
            break
        bounds = window.BoundingRectangle
        if bounds.width() < 700 or bounds.height() < 500:
            raise RuntimeError("3DMark 창이 너무 작습니다. 창을 크게 연 뒤 다시 시도하세요.")
        screenshot = ImageGrab.grab(bbox=(bounds.left, bounds.top, bounds.right, bounds.bottom), all_screens=True)
        found = _match_card(screenshot, template)
        if found and found[0] >= .85:
            _, x, y = found
            if y < 110 or y > screenshot.height - 45:
                raise RuntimeError("Time Spy 항목이 일부 가려져 있어 실행하지 않았습니다.")
            auto.Click(bounds.left + x, bounds.top + y, waitTime=.1)
            return
        # Scroll the benchmark listing only. A changed layout fails closed.
        auto.MoveTo(bounds.left + bounds.width() // 2, bounds.top + bounds.height() // 2)
        auto.WheelDown(wheelTimes=2, waitTime=.1)
        time.sleep(.3)
    raise RuntimeError("3DMark 목록에서 Time Spy 기본 테스트를 찾지 못했습니다.")


def _wait_route(window, expected: str, deadline: float):
    while time.monotonic() < deadline:
        document = _document(window)
        if _route(document).endswith(expected):
            return document
        time.sleep(.25)
    raise RuntimeError("3DMark에서 Time Spy 화면으로 이동하지 못했습니다.")


def _wait_detail_ready(window, deadline: float):
    while time.monotonic() < deadline:
        document = _document(window)
        route = _route(document)
        if "#TEST_DETAILS/" in route and not route.endswith(_DETAIL_ROUTE):
            raise RuntimeError("다른 3DMark 테스트가 선택되어 실행을 중단했습니다.")
        if (route.endswith(_DETAIL_ROUTE)
                and document.TextControl(Name="Time Spy", searchDepth=6).Exists(0)
                and document.HyperlinkControl(AutomationId="tabDetails", searchDepth=6).Exists(0)
                and document.HyperlinkControl(AutomationId="runButton", searchDepth=6).Exists(0)):
            return document
        time.sleep(.25)
    raise RuntimeError("Time Spy 기본 테스트 화면이 완전히 열리지 않았습니다.")


def launch_timespy(executable: str, timeout: float = 120, cancel_event=None) -> None:
    """Launch and click the default Time Spy run button; never run an unknown test."""
    if os.name != "nt":
        raise RuntimeError("Steam판 자동 실행은 Windows에서만 지원합니다.")
    import uiautomation as auto

    exe = Path(executable)
    deadline = time.monotonic() + timeout
    window = _find_window(auto, exe)
    if window is None:
        subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=subprocess.CREATE_NO_WINDOW)
        while time.monotonic() < deadline:
            window = _find_window(auto, exe)
            if window:
                break
            time.sleep(.5)
    if window is None:
        raise RuntimeError("Steam판 3DMark 창이 열리지 않았습니다. Steam 로그인을 확인하세요.")
    window.SetActive(waitTime=.1)
    document = _document(window)
    if not _route(document).endswith(_DETAIL_ROUTE):
        try:
            header = document.GetChildren()[0]
            navigation = header.GetChildren()[1].GetChildren()[0].GetChildren()
        except IndexError as exc:
            raise RuntimeError("3DMark 메뉴 구조가 변경되어 자동 실행을 중단했습니다.") from exc
        if len(navigation) < 2 or header.AutomationId != "header":
            raise RuntimeError("3DMark 메뉴 구조가 변경되어 자동 실행을 중단했습니다.")
        navigation[1].GetChildren()[0].Click(waitTime=.1)
        _wait_route(window, _BENCHMARK_ROUTE, deadline)
        art = exe.parent / "webroot" / "assets" / "img" / "time_spy_380x160.jpg"
        _select_card(auto, window, art, deadline)
    document = _wait_detail_ready(window, deadline)
    details = document.HyperlinkControl(AutomationId="tabDetails", searchDepth=6)
    run = document.HyperlinkControl(AutomationId="runButton", searchDepth=6)
    if not details.Exists(0) or not run.Exists(0):
        raise RuntimeError("Time Spy 기본 실행 버튼을 확인하지 못했습니다.")
    if cancel_event is not None and cancel_event.is_set():
        return
    details.Click(waitTime=.1)
    document = _wait_route(window, _DETAIL_ROUTE, deadline)
    run = document.HyperlinkControl(AutomationId="runButton", searchDepth=6)
    if not run.Exists(0):
        raise RuntimeError("Time Spy 기본 실행 버튼을 확인하지 못했습니다.")
    if cancel_event is not None and cancel_event.is_set():
        return
    run.Click(waitTime=.1)
    # Accept a launch only after the frontend moves to its running/results view.
    while time.monotonic() < deadline:
        if _route(_document(window)).endswith("#RESULTS"):
            return
        time.sleep(.4)
    raise RuntimeError("3DMark가 Time Spy 실행 요청을 받아들이지 않았습니다. 화면을 확인하세요.")
