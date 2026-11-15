"""Parse oMLX server.log benchmark sections."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

BENCH_START = re.compile(
    r"Benchmark started: (bench-[0-9a-f]+)", re.IGNORECASE
)
ANE_CONFIG = re.compile(
    r"\[benchmark-ane-config\].*?\benabled=(True|False)"
)
ANE_SUMMARY = re.compile(
    r"\[benchmark-ane-summary\]\s+(.+)"
)
PP_RESULT = re.compile(
    r"\[benchmark-pp-result\]\s+(.+)"
)
ANE_MLP_OPS = re.compile(r"\[benchmark-ane-profile\].*?category=mlp operations=(\d+)")
KV_LINE = re.compile(
    r"(affine4|affine8|turboquant):\s+converted\s+(\d+)/(\d+)\s+cache layers to\s+([\d.]+)-bit",
    re.IGNORECASE,
)


def _parse_kv_segment(segment: str) -> Dict[str, str]:
    """Parse space-separated key=value tokens from a log segment."""
    out: Dict[str, str] = {}
    for part in segment.split():
        if "=" in part:
            key, _, value = part.partition("=")
            out[key] = value
    return out


def _flush_run(
    runs: Dict[str, Dict[str, Any]],
    bench_id: Optional[str],
    chunk: List[str],
) -> None:
    if not bench_id:
        return
    data: Dict[str, Any] = {
        "bench_id": bench_id,
        "ane_enabled": None,
        "full_ane_tiles": None,
        "gpu_tail_tokens": None,
        "processing_tps": None,
        "gen_tps": None,
        "ttft_ms": None,
        "e2e_ms": None,
        "cached_tokens": None,
        "pp": None,
        "kv_lines": [],
        "ane_mlp_operations": None,
    }
    for line in chunk:
        m = ANE_CONFIG.search(line)
        if m:
            data["ane_enabled"] = m.group(1) == "True"
        m = ANE_SUMMARY.search(line)
        if m:
            parsed = _parse_kv_segment(m.group(1))
            data.update(
                {
                    "pp": _float_or_none(parsed.get("pp")),
                    "full_ane_tiles": _int_or_none(parsed.get("full_ane_tiles")),
                    "gpu_tail_tokens": _int_or_none(parsed.get("gpu_tail_tokens")),
                }
            )
        m = PP_RESULT.search(line)
        if m:
            parsed = _parse_kv_segment(m.group(1))
            data["pp"] = _float_or_none(parsed.get("pp")) or data["pp"]
            data["processing_tps"] = _float_or_none(parsed.get("processing_tps"))
            data["gen_tps"] = _float_or_none(parsed.get("gen_tps"))
            data["ttft_ms"] = _float_or_none(parsed.get("ttft_ms"))
            data["e2e_ms"] = _float_or_none(parsed.get("e2e_ms"))
            data["cached_tokens"] = _int_or_none(parsed.get("cached_tokens"))
        m = ANE_MLP_OPS.search(line)
        if m:
            data["ane_mlp_operations"] = int(m.group(1))
        m = KV_LINE.search(line)
        if m:
            data["kv_lines"].append(
                {
                    "scheme": m.group(1).lower(),
                    "converted": int(m.group(2)),
                    "total": int(m.group(3)),
                    "bits": float(m.group(4)),
                }
            )
    runs[bench_id] = data


def _float_or_none(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_none(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_server_log(text: str) -> Dict[str, Dict[str, Any]]:
    """Return bench_id -> parsed benchmark fields from raw log text."""
    runs: Dict[str, Dict[str, Any]] = {}
    current_id: Optional[str] = None
    chunk: List[str] = []

    for line in text.splitlines():
        m = BENCH_START.search(line)
        if m:
            _flush_run(runs, current_id, chunk)
            current_id = m.group(1)
            chunk = [line]
        elif current_id is not None:
            chunk.append(line)

    _flush_run(runs, current_id, chunk)
    return runs


def read_server_log_since(path: str, offset: int) -> Dict[str, Dict[str, Any]]:
    """Parse only the log bytes written after `offset` (one run's window).

    Falls back to the whole file if the log was rotated (smaller than offset).
    """
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(offset if offset <= size else 0)
        return parse_server_log(fh.read().decode("utf-8", errors="replace"))


def read_server_log(path: str) -> Dict[str, Dict[str, Any]]:
    """Load and parse a server log file from disk."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_server_log(fh.read())