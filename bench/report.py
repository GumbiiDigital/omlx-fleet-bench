#!/usr/bin/env python3
"""Summarize JSONL benchmark results into markdown and SVG charts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

NOISE_SPREAD_THRESHOLD = 0.03


@dataclass
class CellStats:
    machine: str
    model: str
    variant: str
    size: int
    runs_expected: int
    processing_tps: List[float]
    ttft_ms: List[float]
    n_valid: int
    valid_tps: List[float]
    valid_ttft: List[float]

    @property
    def incomplete(self) -> bool:
        return self.n_valid < self.runs_expected

    def spread_pct(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        m = mean(values)
        if m == 0:
            return 0.0
        return (max(values) - min(values)) / m

    @property
    def noisy(self) -> bool:
        if len(self.valid_tps) < 2:
            return False
        return self.spread_pct(self.valid_tps) > NOISE_SPREAD_THRESHOLD


def iter_jsonl_files(results_dir: Path) -> List[Path]:
    return sorted(results_dir.rglob("*.jsonl"))


def load_rows(paths: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    return rows


def metric_from_row(row: Dict[str, Any], key: str) -> Optional[float]:
    metrics = row.get("metrics") or {}
    if key in metrics and metrics[key] is not None:
        return float(metrics[key])
    log = row.get("log") or {}
    if key == "processing_tps" and log.get("processing_tps") is not None:
        return float(log["processing_tps"])
    if key == "ttft_ms" and log.get("ttft_ms") is not None:
        return float(log["ttft_ms"])
    return None


def group_rows(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str, int], CellStats]:
    buckets: DefaultDict[Tuple[str, str, str, int], List[Dict[str, Any]]] = defaultdict(list)
    expected: Dict[Tuple[str, str, str, int], int] = defaultdict(int)

    for row in rows:
        key = (
            str(row.get("machine", "")),
            str(row.get("model", "")),
            str(row.get("variant", "")),
            int(row.get("prompt_size", 0)),
        )
        buckets[key].append(row)

    for key, items in buckets.items():
        from_rows = [int(r["runs_per_cell"]) for r in items if r.get("runs_per_cell")]
        if from_rows:
            expected[key] = from_rows[0]
        else:
            repeats = {int(r.get("repeat_index", 0)) for r in items}
            expected[key] = len(repeats) if repeats else len(items)

    grouped: Dict[Tuple[str, str, str, int], CellStats] = {}
    for key, items in buckets.items():
        machine, model, variant, size = key
        tps_all: List[float] = []
        ttft_all: List[float] = []
        tps_valid: List[float] = []
        ttft_valid: List[float] = []
        n_valid = 0
        for row in items:
            tps = metric_from_row(row, "processing_tps")
            ttft = metric_from_row(row, "ttft_ms")
            if tps is not None:
                tps_all.append(tps)
            if ttft is not None:
                ttft_all.append(ttft)
            if (row.get("validity") or {}).get("valid"):
                n_valid += 1
                if tps is not None:
                    tps_valid.append(tps)
                if ttft is not None:
                    ttft_valid.append(ttft)
        grouped[key] = CellStats(
            machine=machine,
            model=model,
            variant=variant,
            size=size,
            runs_expected=expected.get(key, 3),
            processing_tps=tps_all,
            ttft_ms=ttft_all,
            n_valid=n_valid,
            valid_tps=tps_valid,
            valid_ttft=ttft_valid,
        )
    return grouped


def fmt_stats(values: List[float]) -> Tuple[str, str, str]:
    if not values:
        return "-", "-", "-"
    return (
        f"{mean(values):.1f}",
        f"{min(values):.1f}",
        f"{max(values):.1f}",
    )


def write_summary_md(cells: List[CellStats], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Benchmark summary",
        "",
        "| Machine | Model | Variant | Size | n valid | TPS mean/min/max | TTFT ms mean/min/max | Spread% | Flags |",
        "| --- | --- | --- | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for cell in sorted(cells, key=lambda c: (c.machine, c.model, c.size, c.variant)):
        tps_m, tps_min, tps_max = fmt_stats(cell.valid_tps or cell.processing_tps)
        ttft_m, ttft_min, ttft_max = fmt_stats(cell.valid_ttft or cell.ttft_ms)
        spread = cell.spread_pct(cell.valid_tps) * 100 if cell.valid_tps else 0.0
        flags: List[str] = []
        if cell.noisy:
            flags.append("noisy")
        if cell.incomplete:
            flags.append("incomplete")
        lines.append(
            f"| {cell.machine} | {cell.model} | {cell.variant} | {cell.size} | "
            f"{cell.n_valid}/{cell.runs_expected} | {tps_m}/{tps_min}/{tps_max} | "
            f"{ttft_m}/{ttft_min}/{ttft_max} | {spread:.1f} | {', '.join(flags) or '-'} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_ttft_chart(
    *,
    machine: str,
    model: str,
    size: int,
    variants: List[Tuple[str, float]],
    out_path: Path,
) -> None:
    """Write a simple horizontal bar chart (TTFT seconds) as SVG."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    label_w = 120
    track_w = 400
    bar_h = 28
    gap = 12
    pad = 20
    value_w = 90  # room for the value text after the longest bar
    max_val = max((v for _, v in variants), default=1.0) or 1.0
    height = pad * 2 + len(variants) * (bar_h + gap)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{label_w + track_w + value_w + pad * 2}" height="{height}">',
        f'<text x="{pad}" y="{pad - 4}" font-family="monospace" font-size="12">'
        f"{machine} | {model} | {size} tok — TTFT (s), lower is better</text>",
    ]
    y = pad + 16
    for label, seconds in variants:
        bar_w = int((seconds / max_val) * track_w) if max_val else 0
        parts.append(
            f'<text x="{pad}" y="{y + bar_h - 8}" font-family="monospace" font-size="12" '
            f'text-anchor="start">{label[:14]:14s}</text>'
        )
        x0 = pad + label_w
        parts.append(
            f'<rect x="{x0}" y="{y}" width="{bar_w}" height="{bar_h}" fill="#4a90d9"/>'
        )
        parts.append(
            f'<text x="{x0 + bar_w + 6}" y="{y + bar_h - 8}" font-family="monospace" '
            f'font-size="11">{seconds:.2f}s</text>'
        )
        y += bar_h + gap
    parts.append("</svg>")
    out_path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def build_charts(cells: List[CellStats], charts_dir: Path) -> None:
    by_chart: DefaultDict[Tuple[str, str, int], List[Tuple[str, float]]] = defaultdict(list)
    for cell in cells:
        if not cell.valid_ttft:
            continue
        ttft_s = mean(cell.valid_ttft) / 1000.0
        by_chart[(cell.machine, cell.model, cell.size)].append((cell.variant, ttft_s))

    for (machine, model, size), variants in sorted(by_chart.items()):
        safe_machine = machine.replace("/", "-")
        safe_model = model.replace("/", "-")
        fname = f"{safe_machine}__{safe_model}__{size}.svg"
        write_ttft_chart(
            machine=machine,
            model=model,
            size=size,
            variants=sorted(variants, key=lambda x: x[0]),
            out_path=charts_dir / fname,
        )


def report_all(results_dir: Path, report_dir: Path) -> int:
    paths = iter_jsonl_files(results_dir)
    if not paths:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "summary.md").write_text("# Benchmark summary\n\nNo JSONL files found.\n")
        return 1

    rows = load_rows(paths)
    grouped = group_rows(rows)
    cells = list(grouped.values())

    write_summary_md(cells, report_dir / "summary.md")
    build_charts(cells, report_dir / "charts")

    ok = True
    for cell in cells:
        if cell.incomplete or cell.noisy:
            ok = False
            break
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate benchmark report")
    parser.add_argument(
        "results_dir",
        nargs="?",
        default="results",
        help="Directory containing **/*.jsonl",
    )
    parser.add_argument(
        "--report-dir",
        default="report",
        help="Output directory for summary.md and charts",
    )
    args = parser.parse_args(argv)
    return report_all(Path(args.results_dir), Path(args.report_dir))


if __name__ == "__main__":
    raise SystemExit(main())