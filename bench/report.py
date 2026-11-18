#!/usr/bin/env python3
"""Summarize speed rows (from bench/run.py) into a markdown table and SVG charts.

Usage:
    python3 bench/report.py results/my-mac --report-dir report

It reads every JSONL file under the folder it is given and groups rows by machine, model,
variant and prompt size. To report one study, give it a folder (or a file) that holds only
that study. Exit code 0 means every cell has its planned valid runs and none is noisy.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bench import latency  # noqa: E402
from bench.charts import BarPanel, BarRow, Caption, LinePanel, LinePoint, LineSeries, bar_panels  # noqa: E402
from bench.labels import (  # noqa: E402
    ordered_settings,
    ordered_variants,
    setting_label,
    setting_series,
    size_label,
    variant_label,
    variant_series,
)
from bench.stats import spread  # noqa: E402
from bench.svg import THEMES  # noqa: E402

NOISE_SPREAD_THRESHOLD = 0.03
# Memory is reported in binary gigabytes (2**30 bytes), the unit RAM sizes are quoted in,
# so a figure can be held against "256 GB" of unified memory directly.
BYTES_PER_GB = 2**30

CellKey = Tuple[str, str, str, int]


@dataclass
class CellStats:
    """One cell of a matrix: a variant at a prompt size, on one machine and model."""

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
    valid_peak_bytes: List[float]

    @property
    def incomplete(self) -> bool:
        return self.n_valid < self.runs_expected

    def spread_pct(self, values: List[float]) -> float:
        return spread(values)

    @property
    def noisy(self) -> bool:
        return spread(self.valid_tps) > NOISE_SPREAD_THRESHOLD

    @property
    def mean_tps(self) -> Optional[float]:
        return mean(self.valid_tps) if self.valid_tps else None

    @property
    def mean_ttft_s(self) -> Optional[float]:
        return mean(self.valid_ttft) / 1000.0 if self.valid_ttft else None

    @property
    def mean_peak_gb(self) -> Optional[float]:
        return mean(self.valid_peak_bytes) / BYTES_PER_GB if self.valid_peak_bytes else None


def iter_jsonl_files(results: Path) -> List[Path]:
    if results.is_file():
        return [results]
    return sorted(results.rglob("*.jsonl"))


def load_rows(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def metric_from_row(row: Dict[str, Any], key: str) -> Optional[float]:
    """A metric from the benchmark result, falling back to the parsed server log line."""
    metrics = row.get("metrics") or {}
    if metrics.get(key) is not None:
        return float(metrics[key])
    log = row.get("log") or {}
    if key in ("processing_tps", "ttft_ms") and log.get(key) is not None:
        return float(log[key])
    return None


def _runs_expected(items: List[Dict[str, Any]]) -> int:
    declared = [int(r["runs_per_cell"]) for r in items if r.get("runs_per_cell")]
    if declared:
        return declared[0]
    repeats = {int(r.get("repeat_index", 0)) for r in items}
    return len(repeats) if repeats else len(items)


def group_rows(rows: List[Dict[str, Any]]) -> Dict[CellKey, CellStats]:
    buckets: DefaultDict[CellKey, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if "prompt_size" not in row:
            continue  # not a speed row (answer-quality rows have a task instead)
        key = (
            str(row.get("machine", "")),
            str(row.get("model", "")),
            str(row.get("variant", "")),
            int(row.get("prompt_size", 0)),
        )
        buckets[key].append(row)

    grouped: Dict[CellKey, CellStats] = {}
    for key, items in buckets.items():
        machine, model, variant, size = key
        cell = CellStats(
            machine=machine,
            model=model,
            variant=variant,
            size=size,
            runs_expected=_runs_expected(items),
            processing_tps=[],
            ttft_ms=[],
            n_valid=0,
            valid_tps=[],
            valid_ttft=[],
            valid_peak_bytes=[],
        )
        for row in items:
            tps = metric_from_row(row, "processing_tps")
            ttft = metric_from_row(row, "ttft_ms")
            peak = metric_from_row(row, "peak_memory_bytes")
            valid = bool((row.get("validity") or {}).get("valid"))
            if tps is not None:
                cell.processing_tps.append(tps)
            if ttft is not None:
                cell.ttft_ms.append(ttft)
            if not valid:
                continue
            cell.n_valid += 1
            if tps is not None:
                cell.valid_tps.append(tps)
            if ttft is not None:
                cell.valid_ttft.append(ttft)
            if peak is not None:
                cell.valid_peak_bytes.append(peak)
        grouped[key] = cell
    return grouped


def sort_cells(cells: Iterable[CellStats]) -> List[CellStats]:
    """Machine, model, prompt size, then the fixed variant order."""
    cells = list(cells)
    rank = {name: index for index, name in enumerate(ordered_variants(c.variant for c in cells))}
    return sorted(cells, key=lambda c: (c.machine, c.model, c.size, rank[c.variant]))


def fmt_stats(values: List[float]) -> Tuple[str, str, str]:
    if not values:
        return "-", "-", "-"
    return f"{mean(values):.1f}", f"{min(values):.1f}", f"{max(values):.1f}"


def fmt_seconds(seconds: float) -> str:
    """Three significant figures: 7.79 s, 24.5 s, 638 s."""
    if seconds < 10:
        return f"{seconds:.2f} s"
    if seconds < 100:
        return f"{seconds:.1f} s"
    return f"{seconds:.0f} s"


def summary_markdown(cells: Iterable[CellStats], title: str = "Speed summary") -> str:
    lines = [
        f"# {title}",
        "",
        "Valid runs only. Prefill speed and time to first token are mean/min/max; spread is",
        "(max - min) / mean of prefill speed. Peak memory is MLX active memory for the run.",
        "",
        "| Machine | Model | Variant | Prompt tokens | Valid runs | Prefill tok/s | "
        "Time to first token ms | Spread % | Peak memory GB | Flags |",
        "| --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | --- |",
    ]
    for cell in sort_cells(cells):
        tps = "/".join(fmt_stats(cell.valid_tps or cell.processing_tps))
        ttft = "/".join(fmt_stats(cell.valid_ttft or cell.ttft_ms))
        peak = f"{cell.mean_peak_gb:.1f}" if cell.mean_peak_gb is not None else "-"
        flags = [name for name, on in (("noisy", cell.noisy), ("incomplete", cell.incomplete)) if on]
        lines.append(
            f"| {cell.machine} | {cell.model} | {cell.variant} | {cell.size} | "
            f"{cell.n_valid}/{cell.runs_expected} | {tps} | {ttft} | "
            f"{spread(cell.valid_tps) * 100:.1f} | {peak} | {', '.join(flags) or '-'} |"
        )
    return "\n".join(lines) + "\n"


def _panels(
    cells: Sequence[CellStats],
    baseline: str,
    value_of,
    value_text,
    note_of,
) -> List[BarPanel]:
    """One panel per prompt size, one bar per variant that has a value."""
    series = variant_series(c.variant for c in cells)
    by_size: DefaultDict[int, List[CellStats]] = defaultdict(list)
    for cell in sort_cells(cells):
        if value_of(cell) is not None:
            by_size[cell.size].append(cell)
    panels = []
    for size in sorted(by_size):
        base = next((value_of(c) for c in by_size[size] if c.variant == baseline), None)
        rows = [
            BarRow(
                label=variant_label(cell.variant),
                value=value_of(cell),
                value_text=value_text(value_of(cell)),
                series=series[cell.variant],
                note=note_of(cell, base),
            )
            for cell in by_size[size]
        ]
        panels.append(BarPanel(title=f"{size_label(size)} prompt", rows=rows))
    return panels


def ttft_panels(cells: Sequence[CellStats], baseline: str) -> List[BarPanel]:
    """Time to first token per variant; the note says how many times faster than `baseline`."""

    def note(cell: CellStats, base: Optional[float]) -> str:
        if cell.variant == baseline:
            return "baseline"
        return f"{base / cell.mean_ttft_s:.1f}× faster" if base else ""

    return _panels(cells, baseline, lambda c: c.mean_ttft_s, fmt_seconds, note)


def memory_panels(cells: Sequence[CellStats], baseline: str) -> List[BarPanel]:
    """Peak memory per variant; the note is the change against `baseline`."""

    def note(cell: CellStats, base: Optional[float]) -> str:
        if cell.variant == baseline:
            return "baseline"
        if not base:
            return ""
        change = (cell.mean_peak_gb - base) / base * 100
        return f"{change:+.1f}%".replace("-", "−")

    return _panels(cells, baseline, lambda c: c.mean_peak_gb, lambda gb: f"{gb:.1f} GB", note)


def log_ticks(low: float, high: float) -> List[float]:
    """1, 2 and 5 times each power of ten, where they fall inside `low` to `high`."""
    ticks: List[float] = []
    decade = 1.0
    while decade <= high:
        for factor in (1, 2, 5):
            value = factor * decade
            if low <= value <= high:
                ticks.append(float(value))
        decade *= 10
    return ticks or [low, high]


def ttft_lines(cells: Sequence[CellStats]) -> LinePanel:
    """Time to first token against prompt size, one line per variant, on log axes.

    A cell with a longer wait sits lower on the chart, so a flat line means the wait grows
    with the prompt; the two lines apart means the helper took a share of the work. Cells
    without a valid run are left out, because they have no mean.
    """
    cells = sort_cells(cells)
    sizes = sorted({c.size for c in cells})
    series = variant_series(c.variant for c in cells)
    lines = []
    for variant in ordered_variants(c.variant for c in cells):
        points = [
            LinePoint(c.size, c.mean_ttft_s, size_label(c.size), fmt_seconds(c.mean_ttft_s))
            for c in cells
            if c.variant == variant and c.mean_ttft_s is not None
        ]
        if points:
            lines.append(LineSeries(variant_label(variant), series[variant], points))
    if not lines:
        raise ValueError("no cell has a time to first token")
    waits = [point.y for line in lines for point in line.points]
    return LinePanel(
        title="Time to first token by prompt size",
        x_min=sizes[0],
        x_max=sizes[-1],
        y_min=min(waits),
        y_max=max(waits),
        x_ticks=[(size, size_label(size)) for size in sizes],
        y_ticks=[(tick, f"{tick:g} s") for tick in log_ticks(min(waits), max(waits))],
        series=lines,
    )


def request_markdown(requests: Sequence["latency.Request"], title: str = "Requests") -> str:
    """Every request of a study on one line, with the checks its row failed named.

    A study about waits keeps the rows it cannot use: a request that began before the helper
    session was up is the evidence, not a row to drop. So the list is the whole file, in order.
    """
    lines = [
        f"# {title}",
        "",
        "One line per request, in the order the rows were written. Time to first token is the",
        "server's own figure. A request whose row failed a check stays in the list and names it.",
        "",
        "| Path | Arm | Prompt | Setting | Helper | State at start | Waited s "
        "| Time to first token s | Layers | Cached tokens | Answer correct | Failed checks |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for request in requests:
        correct = "-" if request.correct is None else ("yes" if request.correct else "no")
        cached = "-" if request.cached_tokens is None else str(request.cached_tokens)
        layers = "none" if request.helper_layers is None else str(request.helper_layers)
        lines.append(
            f"| {request.path} | {request.arm} | {size_label(request.size)} "
            f"| {setting_label(request.setting)} | {'on' if request.helper_on else 'off'} "
            f"| {request.helper_state or 'none'} | {request.helper_wait_s:.1f} | {request.ttft_s:.2f} "
            f"| {layers} | {cached} | {correct} | {', '.join(request.failed) or '-'} |"
        )
    return "\n".join(lines) + "\n"


def setting_panels(
    groups: Dict[Tuple[int, str], "latency.Waits"], baseline: Optional[str] = None
) -> List[BarPanel]:
    """One panel per prompt size, one bar per setting; the note compares with `baseline`.

    A size where the baseline was not run gets no note: there is nothing to compare with there,
    and a made-up reference would read as a measurement.
    """
    sizes = sorted({size for size, _ in groups})
    series = setting_series(setting for _, setting in groups)
    panels = []
    for size in sizes:
        base = groups[(size, baseline)].mean_ttft_s if baseline and (size, baseline) in groups else None
        rows = []
        for setting in ordered_settings(name for group_size, name in groups if group_size == size):
            waits = groups[(size, setting)]
            note = ""
            if base:
                note = "baseline" if setting == baseline else f"{base / waits.mean_ttft_s:.1f}× faster"
            rows.append(
                BarRow(
                    label=setting_label(setting),
                    value=waits.mean_ttft_s,
                    value_text=fmt_seconds(waits.mean_ttft_s),
                    series=series[setting],
                    note=note,
                )
            )
        panels.append(BarPanel(title=f"{size_label(size)} prompt", rows=rows))
    return panels


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "-" for ch in text)


def write_charts(cells: Sequence[CellStats], charts_dir: Path) -> List[Path]:
    """One time-to-first-token chart per machine and model, in a light and a dark theme."""
    groups: DefaultDict[Tuple[str, str], List[CellStats]] = defaultdict(list)
    for cell in cells:
        groups[(cell.machine, cell.model)].append(cell)
    written: List[Path] = []
    for (machine, model), members in sorted(groups.items()):
        variants = ordered_variants(c.variant for c in members)
        if not variants:
            continue
        baseline = "gpu" if "gpu" in variants else variants[0]
        panels = ttft_panels(members, baseline)
        if not panels:
            continue
        caption = Caption(
            title="Time to first token",
            subtitle=[f"{machine} · {model} · mean of valid runs · lower is better"],
        )
        for theme in THEMES.values():
            path = charts_dir / f"{_safe_name(machine)}__{_safe_name(model)}-ttft-{theme.name}.svg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(bar_panels(caption, panels, theme), encoding="utf-8")
            written.append(path)
    return written


def report_all(results: Path, report_dir: Path) -> int:
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = iter_jsonl_files(results)
    if not paths:
        (report_dir / "summary.md").write_text("# Speed summary\n\nNo JSONL files found.\n", encoding="utf-8")
        return 1
    cells = list(group_rows(load_rows(paths)).values())
    (report_dir / "summary.md").write_text(summary_markdown(cells), encoding="utf-8")
    write_charts(cells, report_dir / "charts")
    return 1 if any(cell.incomplete or cell.noisy for cell in cells) else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize speed rows into a table and charts")
    parser.add_argument(
        "results",
        nargs="?",
        default="results",
        help="a JSONL file, or a folder searched for **/*.jsonl",
    )
    parser.add_argument("--report-dir", default="report", help="where summary.md and charts/ go")
    args = parser.parse_args(argv)
    return report_all(Path(args.results), Path(args.report_dir))


if __name__ == "__main__":
    raise SystemExit(main())
