"""result_reader.py — read a 3DMark Time Spy .3dmark-result ZIP and extract scores/temperatures."""

from __future__ import annotations

import csv
import io
import math
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_BENCHMARK = "Time Spy"
_MAX_XML_BYTES = 1_048_576          # 1 MiB
_MAX_CSV_BYTES = 8 * 1024 * 1024    # 8 MiB
_MAX_TOTAL_UNCOMPRESSED = 32 * 1024 * 1024  # 32 MiB
_MAX_ENTRIES = 100
_MAX_SCORE = 1_000_000

_REQUIRED_TAGS = (
    "TimeSpyPerformance3DMarkScore",
    "TimeSpyPerformanceGraphicsScore",
    "TimeSpyPerformanceCPUScore",
)

_FORBIDDEN_DOCTYPE_RE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)
_FORBIDDEN_ENTITY_RE = re.compile(rb"<!ENTITY", re.IGNORECASE)


def _check_zip_path(name: str) -> None:
    """Reject absolute paths, drive letters, and parent-directory traversal."""
    if name.startswith(("/", "\\")):
        raise ValueError(f"suspicious zip path: {name!r}")
    parts = name.replace("\\", "/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"suspicious zip path: {name!r}")
    if ":" in parts[0]:
        raise ValueError(f"suspicious zip path (drive letter): {name!r}")


def _read_entry(zf: zipfile.ZipFile, name: str, max_bytes: int) -> bytes:
    info = zf.getinfo(name)
    if info.file_size > max_bytes:
        raise ValueError(f"{name} exceeds size limit ({info.file_size} > {max_bytes})")
    data = zf.read(name)
    if len(data) > max_bytes:
        raise ValueError(f"{name} decompressed size exceeds limit")
    return data


def _parse_scores(xml_bytes: bytes) -> dict[str, int]:
    scan_bytes = xml_bytes.replace(b'\x00', b'')
    if _FORBIDDEN_DOCTYPE_RE.search(scan_bytes):
        raise ValueError("Result.xml contains <!DOCTYPE>")
    if _FORBIDDEN_ENTITY_RE.search(scan_bytes):
        raise ValueError("Result.xml contains <!ENTITY>")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"malformed Result.xml: {exc}") from exc

    tag_map: dict[str, list[ET.Element]] = {}
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        tag_map.setdefault(tag, []).append(el)

    scores: dict[str, int] = {}
    for tag in _REQUIRED_TAGS:
        els = tag_map.get(tag, [])
        if not els:
            raise ValueError(f"missing required tag {tag!r}; not a valid Time Spy result")
        if len(els) > 1:
            raise ValueError(f"duplicate tag {tag!r} in Result.xml")
        text = (els[0].text or "").strip()
        try:
            val = int(text)
        except ValueError:
            raise ValueError(f"non-integer score for {tag}: {text!r}") from None
        if val < 0 or val > _MAX_SCORE or not math.isfinite(val):
            raise ValueError(f"score out of range for {tag}: {val}")
        scores[tag] = val

    return scores


def _collect_temperatures(csv_bytes: bytes) -> dict[str, float]:
    temps: dict[str, float] = {}
    text = csv_bytes.decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text), delimiter=';' if ';' in text.partition('\n')[0] else ',')
    header = next(reader, None)
    if not header:
        return temps

    col_idx: dict[int, str] = {}
    for i, h in enumerate(header):
        hl = h.strip().lower()
        # Raw vendor channel names do not establish units or sample semantics.
        # Only expose explicitly Celsius-labeled columns; keep others unknown.
        if not re.search(r'\(c\)|°c|\bcelsius\b', hl):
            continue
        if "gpu" in hl and "temp" in hl:
            col_idx[i] = "gpuMax"
        elif "cpu" in hl and "temp" in hl:
            col_idx[i] = "cpuMax"

    if not col_idx:
        return temps

    for row in reader:
        for idx, key in col_idx.items():
            if idx >= len(row):
                continue
            raw = row[idx].strip()
            if not raw:
                continue
            try:
                v = float(raw)
            except ValueError:
                continue
            if math.isfinite(v) and 0.0 < v <= 150.0:
                temps[key] = max(temps.get(key, v), v)

    return temps


def _parse_result(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"not a file: {p.name}")

    if p.stat().st_size > _MAX_TOTAL_UNCOMPRESSED:
        raise ValueError('archive file exceeds size limit')
    with zipfile.ZipFile(p, "r") as zf:
        names = zf.namelist()
        if len(names) > _MAX_ENTRIES:
            raise ValueError(f"too many entries in archive: {len(names)}")

        total_uncompressed = 0
        for info in zf.infolist():
            _check_zip_path(info.filename)
            total_uncompressed += info.file_size
        if total_uncompressed > _MAX_TOTAL_UNCOMPRESSED:
            raise ValueError("archive uncompressed size exceeds 32 MiB")

        xml_names = [n for n in names if n == "Result.xml"]
        if len(xml_names) != 1:
            raise ValueError(f"expected exactly one Result.xml, found {len(xml_names)}")
        xml_bytes = _read_entry(zf, xml_names[0], _MAX_XML_BYTES)

        scores = _parse_scores(xml_bytes)

        temps: dict[str, float] = {}
        csv_names = [n for n in names if n.lower().endswith("monitoring.csv")]
        if csv_names:
            if len(csv_names) > 1:
                raise ValueError("multiple Monitoring.csv entries")
            csv_bytes = _read_entry(zf, csv_names[0], _MAX_CSV_BYTES)
            temps = _collect_temperatures(csv_bytes)

    total = scores["TimeSpyPerformance3DMarkScore"]
    graphics = scores["TimeSpyPerformanceGraphicsScore"]
    cpu = scores["TimeSpyPerformanceCPUScore"]

    status = "valid" if (total > 0 and graphics > 0 and cpu > 0) else "failed"

    return {
        "totalScore": total,
        "graphicsScore": graphics,
        "cpuScore": cpu,
        "status": status,
        "benchmark": _BENCHMARK,
        "temperatures": temps,
    }


def parse_result(path: str | Path) -> dict:
    try:
        return _parse_result(path)
    except (zipfile.BadZipFile, RuntimeError, KeyError, ET.ParseError) as exc:
        raise ValueError('invalid 3DMark result archive') from exc
