#!/usr/bin/env python3
"""Rebuild every published number from the raw rows: README tables, reports and charts.

Usage:
    python3 bench/publish.py            # write charts/, reports/ and the README tables
    python3 bench/publish.py --check    # change nothing; exit 1 if anything is out of date

`results/published.json` lists which raw files make up each published study. Nothing in
the README tables or the charts is typed by hand: this script computes it, and `--check`
proves the committed files still match the rows.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bench import latency, quality_report, report, waves  # noqa: E402
from bench.charts import (  # noqa: E402
    Caption,
    IntervalPanel,
    IntervalRow,
    bar_panels,
    interval_panels,
    line_panel,
    line_panels,
)
from bench.labels import (  # noqa: E402
    arm_label,
    ordered_arms,
    ordered_settings,
    ordered_variants,
    setting_label,
    size_label,
    variant_label,
    variant_series,
)
from bench.stats import spread, wilson_interval  # noqa: E402
from bench.svg import THEMES  # noqa: E402

MANIFEST = "results/published.json"
README = "README.md"
TASK_LABELS = {"gsm8k": "GSM8K", "mmlu": "MMLU", "passkey": "Passkey"}
# A task with fewer samples than this gets no interval in the chart; it goes in the table.
MIN_SAMPLES_FOR_INTERVAL = 30

BLOCK = re.compile(
    r"(<!-- BEGIN GENERATED: (?P<id>[^>]+?) -->\n)(?P<body>.*?)(<!-- END GENERATED: (?P=id) -->)",
    re.S,
)

Outputs = Dict[str, str]  # repo-relative path -> file content


class PublishError(Exception):
    """The manifest, the rows and the README do not fit together."""


def _rows(root: Path, files: Sequence[str]) -> List[Dict[str, Any]]:
    paths = [root / name for name in files]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise PublishError(f"listed in {MANIFEST} but missing: {missing}")
    return report.load_rows(paths)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _minus(text: str) -> str:
    return text.replace("-", "−")


def _charts(name: str, build) -> Outputs:
    return {f"charts/{name}-{theme.name}.svg": build(theme) for theme in THEMES.values()}


def _cells(rows: List[Dict[str, Any]], machine: str) -> List[report.CellStats]:
    cells = [c for c in report.group_rows(rows).values() if c.machine == machine]
    if not cells:
        raise PublishError(f"no speed rows for machine {machine!r}")
    broken = [f"{c.variant}:{c.size}" for c in cells if c.incomplete]
    if broken:
        raise PublishError(f"{machine}: cells without their planned valid runs: {broken}")
    return cells


def _lookup(cells: Sequence[report.CellStats]) -> Dict[Tuple[str, int], report.CellStats]:
    return {(c.variant, c.size): c for c in cells}


def build_speed(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Time to first token and prefill speed per setup and prompt size."""
    study, label, baseline = machine["speed"], machine["label"], machine["speed"]["baseline"]
    cells = _cells(_rows(root, study["files"]), label)
    by = _lookup(cells)
    variants = ordered_variants(c.variant for c in cells)
    sizes = sorted({c.size for c in cells})
    header = ["Setup"] + [size_label(s) for s in sizes]

    def ttft(variant: str, size: int) -> str:
        cell, base = by[(variant, size)], by[(baseline, size)]
        text = f"{cell.mean_ttft_s:.1f} s"
        return text if variant == baseline else f"{text} · {base.mean_ttft_s / cell.mean_ttft_s:.1f}×"

    ttft_rows = [[variant_label(v)] + [ttft(v, s) for s in sizes] for v in variants]
    tps_rows = [[variant_label(v)] + [f"{by[(v, s)].mean_tps:,.0f}" for s in sizes] for v in variants]
    noisy = [c for c in report.sort_cells(cells) if c.noisy]
    quiet = max(spread(c.valid_tps) for c in cells if not c.noisy) * 100
    lines = [
        f"Time to first token, and how many times shorter the wait is than {variant_label(baseline)}:",
        "",
        _table(header, ttft_rows),
        "",
        "Prefill speed in tokens per second:",
        "",
        _table(header, tps_rows),
        "",
    ]
    spread_line = f"Run-to-run spread of prefill speed is at most {quiet:.1f}% in every cell"
    if noisy:
        named = ", ".join(
            f"{variant_label(c.variant)} at {size_label(c.size)} ({spread(c.valid_tps) * 100:.1f}%)" for c in noisy
        )
        spread_line += f" except {named}"
    lines.append(spread_line + ".")
    if study.get("warm_rerun"):
        warm = report.sort_cells(_cells(_rows(root, study["warm_rerun"]), label))
        again = ", ".join(
            f"{variant_label(c.variant)} at {size_label(c.size)}: {c.mean_tps:,.0f} tok/s "
            f"({by[(c.variant, c.size)].mean_tps:,.0f} in the first pass)"
            for c in warm
        )
        lines.append(f"Re-run back to back, {warm[0].n_valid} runs each: {again}.")

    caption = Caption(
        title="Time to first token by prompt size",
        subtitle=[f"{machine['model']} · {machine['hardware']} · helper: {machine['helper']}", study["conditions"]],
        footnotes=[f"Each panel has its own scale. “× faster” compares with {variant_label(baseline)} at the same prompt size."],
    )
    panels = report.ttft_panels(cells, baseline)
    outputs = _charts(f"{label}-ttft", lambda theme: bar_panels(caption, panels, theme))
    outputs[f"reports/{label}/speed.md"] = report.summary_markdown(cells, "Speed: every cell")
    return outputs, "\n".join(lines)


def build_kv_cache(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Peak memory and speed per KV cache scheme."""
    study, label, baseline = machine["kv_cache"], machine["label"], machine["kv_cache"]["baseline"]
    cells = _cells(_rows(root, study["files"]), label)
    by = _lookup(cells)
    variants = ordered_variants(c.variant for c in cells)
    sizes = sorted({c.size for c in cells})

    def change(value: float, base: float) -> str:
        return _minus(f"{(value - base) / base * 100:+.1f}%")

    header = ["Scheme"]
    for size in sizes:
        header += [f"{size_label(size)} peak memory", f"{size_label(size)} time to first token"]
    rows = []
    for variant in variants:
        row = [variant_label(variant)]
        for size in sizes:
            cell, base = by[(variant, size)], by[(baseline, size)]
            memory, wait = f"{cell.mean_peak_gb:.1f} GB", f"{cell.mean_ttft_s:.1f} s"
            if variant != baseline:
                memory += f" · {change(cell.mean_peak_gb, base.mean_peak_gb)}"
                wait += f" · {change(cell.mean_ttft_s, base.mean_ttft_s)}"
            row += [memory, wait]
        rows.append(row)
    worst = max(spread(c.valid_tps) for c in cells) * 100
    body = "\n".join(
        [_table(header, rows), "", f"Run-to-run spread of prefill speed is at most {worst:.2f}% in every cell."]
    )

    caption = Caption(
        title="Peak memory by KV cache scheme",
        subtitle=[f"{machine['model']} · {machine['hardware']}", study["conditions"]],
        footnotes=["Peak MLX active memory during the run, not the size of the KV cache alone. 1 GB = 2³⁰ bytes."],
    )
    panels = report.memory_panels(cells, baseline)
    outputs = _charts(f"{label}-kv-memory", lambda theme: bar_panels(caption, panels, theme))
    outputs[f"reports/{label}/kv-cache.md"] = report.summary_markdown(cells, "KV cache: every cell")
    return outputs, body


def _axis(lows: Sequence[float]) -> Tuple[float, List[float]]:
    """Axis start and ticks, in percent, for accuracies that end at 100."""
    start = max(0.0, (int(min(lows)) // 5) * 5.0)
    step = 5.0 if 100 - start <= 30 else 10.0
    ticks = [start]
    while ticks[-1] + step <= 100:
        ticks.append(ticks[-1] + step)
    return start, ticks


def build_quality(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Accuracy per setting and task, with paired changes against the baseline setting."""
    study, label, baseline = machine["quality"], machine["label"], machine["quality"]["baseline"]
    rows = [r for r in _rows(root, study["files"]) if r.get("machine") == label]
    try:
        rows = quality_report.apply_replacements(rows, _rows(root, study.get("replace", [])))
    except ValueError as exc:
        raise PublishError(str(exc)) from None
    errors = sum(1 for r in rows if r.get("status") == "error")
    if errors:
        raise PublishError(f"{label}: {errors} quality rows are errors")
    groups = quality_report.group(rows)
    variants = ordered_variants(v for v, _ in groups)
    tasks = [t for t in TASK_LABELS if any(task == t for _, task in groups)]
    tasks += sorted({task for _, task in groups} - set(tasks))
    scores = {key: quality_report.accuracy(items) for key, items in groups.items()}
    changes = quality_report.changes_against(rows, baseline)
    charted = [t for t in tasks if scores[(baseline, t)][1] >= MIN_SAMPLES_FOR_INTERVAL]

    header = ["Setting"] + [f"{TASK_LABELS.get(t, t)} (of {scores[(baseline, t)][1]})" for t in tasks]
    header += [f"Answers changed against {variant_label(baseline)}", "Still cut off"]
    table = []
    for variant in variants:
        row = [variant_label(variant)]
        for task in tasks:
            correct, scored = scores[(variant, task)]
            row.append(f"{correct} · {correct / scored * 100:.1f}%" if task in charted else str(correct))
        if variant == baseline:
            row.append("baseline")
        else:
            moved = [changes[(variant, t)] for t in charted]
            row.append(
                f"{sum(m.lost for m in moved)} lost, {sum(m.gained for m in moved)} gained "
                f"(of {sum(m.compared for m in moved)})"
            )
        row.append(str(sum(quality_report.capped(groups[(variant, t)]) for t in tasks)))
        table.append(row)
    body = _table(header, table)

    series = variant_series(variants)
    panels, lows = [], []
    for task in charted:
        panel_rows = []
        for variant in variants:
            correct, scored = scores[(variant, task)]
            low, high = (bound * 100 for bound in wilson_interval(correct, scored))
            lows.append(low)
            panel_rows.append(
                IntervalRow(
                    label=variant_label(variant),
                    value=correct / scored * 100,
                    low=low,
                    high=high,
                    value_text=f"{correct / scored * 100:.1f}%",
                    series=series[variant],
                    note=f"{correct}/{scored}",
                )
            )
        panels.append(
            IntervalPanel(title=f"{TASK_LABELS.get(task, task)} · {scores[(baseline, task)][1]} questions", rows=panel_rows)
        )
    axis_min, ticks = _axis(lows)
    footnotes = ["Dot: share of correct answers. Line: 95% Wilson interval for that share. The axis does not start at zero."]
    for task in tasks:
        if task in charted:
            continue
        parts = sorted({scores[(v, task)] for v in variants})
        if len(parts) == 1:
            footnotes.append(f"{TASK_LABELS.get(task, task)}: {parts[0][0]} of {parts[0][1]} correct under every setting.")
    caption = Caption(
        title="Answer accuracy by setting",
        subtitle=[f"{machine['model']} · {machine['hardware']}", study["conditions"]],
        footnotes=footnotes,
    )
    outputs = _charts(
        f"{label}-quality",
        lambda theme: interval_panels(
            caption, panels, theme, axis_min=axis_min, axis_max=100.0, ticks=ticks, tick_suffix="%"
        ),
    )
    outputs[f"reports/{label}/quality.md"] = quality_report.write_summary(rows)
    return outputs, body


def build_speed_sweep(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Time to first token at each prompt size, Mac alone against the helper.

    The same cells as the speed study, read one prompt size to a line: what changes as the
    prompt grows, not what changes between setups at one size.
    """
    study, label, baseline = machine["speed_sweep"], machine["label"], machine["speed_sweep"]["baseline"]
    cells = _cells(_rows(root, study["files"]), label)
    by = _lookup(cells)
    sizes = sorted({c.size for c in cells})
    helper = next((c.variant for c in cells if c.variant != baseline), None)
    if helper is None:
        raise PublishError(f"{label}: the sweep needs a second setup to compare with {baseline!r}")

    rows = []
    for size in sizes:
        alone, helped = by[(baseline, size)].mean_ttft_s, by[(helper, size)].mean_ttft_s
        if alone is None or helped is None:
            raise PublishError(f"{label}: no time to first token at {size_label(size)}")
        rows.append([size_label(size), f"{alone:.1f} s", f"{helped:.1f} s", f"{alone / helped:.1f}×"])
    header = ["Prompt", variant_label(baseline), variant_label(helper), "Speed-up"]
    pairs = sorted({(c.n_valid, c.runs_expected) for c in cells})
    counts = (
        f"Mean of {pairs[0][0]} valid runs per cell."
        if len(pairs) == 1
        else "Valid runs per cell: " + ", ".join(f"{n} of {planned}" for n, planned in pairs) + "."
    )
    lines = [
        "Time to first token at each prompt size, and how many times shorter the wait is with the helper:",
        "",
        _table(header, rows),
        "",
        counts,
    ]

    caption = Caption(
        title="Time to first token by prompt size",
        subtitle=[f"{machine['model']} · {machine['hardware']} · helper: {machine['helper']}", study["conditions"]],
        footnotes=["Both axes are log scale. One line per setup; hover a point for its value."],
    )
    panel = report.ttft_lines(cells)
    outputs = _charts(f"{label}-ttft-sweep", lambda theme: line_panel(caption, panel, theme))
    outputs[f"reports/{label}/speed-sweep.md"] = report.summary_markdown(cells, "Prompt-size sweep: every cell")
    return outputs, "\n".join(lines)


def _requests(root: Path, study: Dict[str, Any], machine: str) -> List[latency.Request]:
    """Every request of a request-level study, each in the path and arm its file names."""
    requests: List[latency.Request] = []
    for arm in study["arms"]:
        rows = [row for row in _rows(root, [arm["file"]]) if row.get("machine") == machine]
        if not rows:
            raise PublishError(f"{machine}: {arm['file']} holds no request for this machine")
        requests += [latency.from_row(row, path=arm["path"], arm=arm["arm"]) for row in rows]
    return requests


def _reading_line(requests: Sequence[latency.Request]) -> str:
    """One sentence on the cold cache and the answers, counted from the rows.

    A speed-test row has no answer of its own, so answers are counted only where a row records
    one; the sentence then says how many that was rather than implying the rest were wrong.
    """
    total = len(requests)
    cold = sum(1 for request in requests if request.cached_tokens == 0)
    answered = [request for request in requests if request.correct is not None]
    right = sum(1 for request in answered if request.correct)
    if cold == total and len(answered) == total and right == total:
        return f"All {total} requests read their prompt cold and got a correct answer."
    if cold == total:
        return f"Every request read its prompt cold; {right} of {len(answered)} answers were correct."
    return (
        f"{cold} of {total} requests read their prompt cold; "
        f"{right} of {len(answered)} answers were correct."
    )


def _layers_across_sizes(groups: Dict[Tuple[int, str], latency.Waits], setting: str, sizes: Sequence[int]) -> str:
    """The layer count the helper took, saying which prompt size when it differed between them."""
    texts = [
        (size_label(size), groups[(size, setting)].layers_text) for size in sizes if (size, setting) in groups
    ]
    if not texts:
        return "none"
    if len({text for _, text in texts}) == 1:
        return texts[0][1]
    return "; ".join(f"{label}: {text}" for label, text in texts)


def _not_valid_line(path: str, arm: str, flagged: "latency.Waits", alone: Dict[int, float]) -> str:
    """One sentence on the rows a flag marks not valid, saying what their waits measured.

    The helper state at the start alone does not say who served the request: a request that goes
    out while the session is still starting can be read by the Mac alone or by the helper. The
    measured wait is what tells them apart, so the sentence is built from it, never from the state.
    """
    on_the_helper = flagged.at_helper_speed(alone)
    waits = f"{flagged.low_ttft_s:.2f} to {flagged.high_ttft_s:.2f} s"
    if on_the_helper == flagged.requests:
        ran = f"ran at helper speed ({waits})"
    elif on_the_helper == 0:
        ran = f"ran at the speed of the Mac alone ({waits})"
    else:
        ran = f"{on_the_helper} of {flagged.requests} ran at helper speed"
    return (
        f"{flagged.requests} requests in {path} / {arm} are marked not valid by "
        f"`helper_ready_at_start`: they began at helper state {flagged.state_text} and {ran}."
    )


def build_helper_ready(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """What the first request after a settings switch waited, one line per path and arm.

    The switch unloads the model, loads it again and starts a new helper session. A request that
    goes out before that session is up has no error and no warning either way: on the chat path it
    was read by the Mac alone, on the server's speed-test call by the helper. So the study records
    the helper state at the start of each request and reads the wait it got.
    """
    study, label = machine["helper_ready"], machine["label"]
    requests = _requests(root, study, label)
    helped = [request for request in requests if request.helper_on]
    groups = latency.group_requests(helped, lambda request: (request.path, request.arm))
    alone = latency.mac_alone_wait_s(helped)

    header = [
        "Path",
        "Arm",
        "Helper-on requests",
        "Helper state at start",
        "Not valid",
        "Waited (mean)",
        "Time to first token",
        "Ran at helper speed",
    ]
    rows = []
    for arm in study["arms"]:
        key = (arm["path"], arm["arm"])
        waits = groups.get(key)
        if waits is None:
            raise PublishError(f"{label}: no helper-on request for {key[0]}, {key[1]}")
        rows.append(
            [
                key[0],
                key[1],
                str(waits.requests),
                waits.state_text,
                waits.failed_text,
                f"{waits.mean_wait_s:.1f} s",
                f"{waits.low_ttft_s:.2f} to {waits.high_ttft_s:.2f} s",
                f"{waits.at_helper_speed(alone)} of {waits.requests}",
            ]
        )

    lines = [
        "Time to first token of a helper-on request at 32K, after a switch from helper off to helper on:",
        "",
        _table(header, rows),
        "",
    ]
    for arm in study["arms"]:
        waits = groups[(arm["path"], arm["arm"])]
        on_the_mac = waits.requests - waits.at_helper_speed(alone)
        if on_the_mac:
            lines.append(
                f"{arm['path']}, {arm['arm']}: {on_the_mac} of {waits.requests} requests ran at the "
                "speed of the Mac alone."
            )
    not_ready = sum(1 for request in requests if "helper_ready_at_start" in request.failed)
    if not_ready:
        for arm in study["arms"]:
            waits = groups[(arm["path"], arm["arm"])]
            flagged = latency.Waits([member for member in waits.members if "helper_ready_at_start" in member.failed])
            if flagged.requests:
                lines.append(_not_valid_line(arm["path"], arm["arm"], flagged, alone))
    # The helper-off requests are there to force the switch; the cache and answer counts are the
    # helper-on ones, because those are the requests the table is about.
    lines.append(_reading_line(helped))

    outputs: Outputs = {
        f"reports/{label}/helper-ready.md": report.request_markdown(
            requests, "Helper-ready replay: every request"
        )
    }
    return outputs, "\n".join(lines)


def build_helper_layers(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Time to first token per helper layer count, at each prompt size, against the Mac alone."""
    study, label = machine["helper_layers"], machine["label"]
    requests = _requests(root, study, label)
    groups = latency.group_requests(requests, lambda request: (request.size, request.setting))
    sizes = sorted({request.size for request in requests})
    baseline = next((request.setting for request in requests if not request.helper_on), None)
    if baseline is None:
        raise PublishError(f"{label}: the layer study needs a request with the helper off to compare with")
    reference = min(size for size in sizes if (size, baseline) in groups)
    base = groups[(reference, baseline)].mean_ttft_s

    header = ["Setting"] + [f"{size_label(size)} time to first token" for size in sizes]
    header += ["Helper layers", f"Faster than {setting_label(baseline)} at {size_label(reference)}"]
    rows = []
    for setting in ordered_settings(name for _, name in groups):
        row = [setting_label(setting)]
        for size in sizes:
            waits = groups.get((size, setting))
            row.append(
                "not run"
                if waits is None
                else f"{waits.mean_ttft_s:.1f} s ({waits.low_ttft_s:.2f} to {waits.high_ttft_s:.2f})"
            )
        row.append(_layers_across_sizes(groups, setting, sizes))
        if setting == baseline:
            row.append("baseline")
        elif (reference, setting) in groups:
            row.append(f"{base / groups[(reference, setting)].mean_ttft_s:.1f}×")
        else:
            row.append("-")
        rows.append(row)

    counts = sorted({waits.requests for waits in groups.values()})
    count_line = (
        f"Mean of {counts[0]} requests per cell."
        if len(counts) == 1
        else "Requests per cell: " + ", ".join(str(count) for count in counts) + "."
    )
    lines = [
        "Time to first token per helper layer count, and how many times faster than the Mac alone "
        f"at {size_label(reference)}:",
        "",
        _table(header, rows),
        "",
        count_line,
        _reading_line(requests),
    ]

    caption = Caption(
        title="Time to first token by helper layer count",
        subtitle=[f"{machine['model']} · {machine['hardware']} · helper: {machine['helper']}", study["conditions"]],
        footnotes=[
            "Each panel has its own scale. “× faster” compares with the Mac alone at the same prompt size.",
            "A pinned count is the number of layers the helper was asked for; the table gives the number it held.",
        ],
    )
    panels = report.setting_panels(groups, baseline)
    outputs = _charts(f"{label}-helper-layers", lambda theme: bar_panels(caption, panels, theme))
    outputs[f"reports/{label}/helper-layers.md"] = report.request_markdown(
        requests, "Helper layer count: every request"
    )
    return outputs, "\n".join(lines)


@dataclass(frozen=True)
class Study:
    """A published study: the shape of its rows, and the builder that reads them."""

    kind: str  # "speed", "quality" or "request": what one row of the study measures
    build: Callable[[Path, Dict[str, Any]], Tuple[Outputs, str]]


def _users_note(counts: Sequence[int]) -> str:
    """'1, 2, 4 and 8 users' — the user counts of the waves, in one phrase."""
    if len(counts) == 1:
        return f"{counts[0]} users"
    return ", ".join(str(count) for count in counts[:-1]) + f" and {counts[-1]} users"


def _wave_cells(rows: List[Dict[str, Any]], label: str) -> List["waves.WaveCell"]:
    """Every cell of a many-users study, checked to cover each prompt size, user count and arm."""
    cells = waves.sort_cells(list(waves.cells(rows).values()))
    if not cells:
        raise PublishError(f"{label}: no many-users request for this machine")
    arms = ordered_arms(cell.arm for cell in cells)
    if len(arms) < 2:
        raise PublishError(f"{label}: the wave study needs a second arm to compare with {arms[0]!r}")
    wanted = {
        (size, users, arm)
        for size in {cell.size for cell in cells}
        for users in {cell.users for cell in cells}
        for arm in arms
    }
    missing = sorted(wanted - {(cell.size, cell.users, cell.arm) for cell in cells})
    if missing:
        raise PublishError(
            f"{label}: cells without a wave: "
            + ", ".join(f"{size_label(size)} / {users} users / {arm_label(arm)}" for size, users, arm in missing)
        )
    return cells


def build_many_users(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Time for a wave of many requests at once, the Mac alone against the helper.

    A many-users row is one request of a wave: N requests that begin at one moment. The cell comes
    from the row's own fields (prompt size, user count, whether the helper was on, which wave), so
    no variant name is typed in. Two figures are the study's own: the wall time of the whole wave,
    which every row of that wave carries, and the prompt tokens of all users together over it.
    """
    study, label = machine["many_users"], machine["label"]
    cells = _wave_cells([row for row in _rows(root, study["files"]) if row.get("machine") == label], label)
    baseline = ordered_arms(cell.arm for cell in cells)[0]
    by = {(cell.size, cell.users, cell.arm): cell for cell in cells}
    sizes = sorted({cell.size for cell in cells})
    counts = sorted({cell.users for cell in cells})

    header = [
        "Prompt",
        "Users",
        "Arm",
        "Requests",
        "Valid",
        "Time to first token",
        "Wave time",
        "Wave prompt tokens/s",
        "Wave speed-up",
    ]
    rows = []
    for size in sizes:
        for users in counts:
            for arm in ordered_arms(cell.arm for cell in cells):
                cell, base = by[(size, users, arm)], by[(size, users, baseline)]
                faster = "baseline" if arm == baseline else f"{waves.comparison(cell, base):.2f}×"
                rows.append(
                    [
                        size_label(size),
                        str(users),
                        arm_label(arm),
                        str(cell.requests),
                        str(cell.n_valid),
                        f"{cell.mean_ttft_s:.2f} s ({cell.low_ttft_s:.2f} to {cell.high_ttft_s:.2f})",
                        f"{cell.mean_wall_s:.1f} s",
                        f"{cell.mean_prompt_tps:,.0f}",
                        faster,
                    ]
                )

    waves_per_cell = sorted({len(cell.waves) for cell in cells})
    count_line = (
        f"Mean of {waves_per_cell[0]} waves per cell, at {_users_note(counts)} per wave."
        if len(waves_per_cell) == 1
        else "Waves per cell: " + ", ".join(str(count) for count in waves_per_cell) + "."
    )
    lines = [
        "Time for the whole wave to finish, at each prompt size, user count and arm:",
        "",
        _table(header, rows),
        "",
        count_line,
    ]

    members = [member for cell in cells for member in cell.members]
    marked = waves.failed_marks(members)
    if marked:
        counts_text = ", ".join(f"{count} · {name}" for name, count in sorted(marked.items()))
        lines.append(f"Requests marked not valid by a check, kept in their wave's count and out of its means: {counts_text}.")
    lines.append(waves.reading_line(members))

    panels = report.wave_lines(cells)
    caption = Caption(
        title="Wave time by number of users",
        subtitle=[f"{machine['model']} · {machine['hardware']} · helper: {machine['helper']}", study["conditions"]],
        footnotes=[
            "Both axes are log scale and shared by both panels. One line per arm; hover a point for its value.",
            "A wave is its user count of requests released together. Lower is better.",
        ],
    )
    outputs = _charts(f"{label}-many-users", lambda theme: line_panels(caption, panels, theme))
    outputs[f"reports/{label}/many-users.md"] = report.wave_markdown(cells)
    return outputs, "\n".join(lines)


STUDIES = {
    "speed": Study("speed", build_speed),
    "speed_sweep": Study("speed", build_speed_sweep),
    "kv_cache": Study("speed", build_kv_cache),
    "quality": Study("quality", build_quality),
    "helper_ready": Study("request", build_helper_ready),
    "helper_layers": Study("request", build_helper_layers),
    "many_users": Study("request", build_many_users),
}


def build(root: Path) -> Tuple[Outputs, Dict[str, str]]:
    """Every generated file, and every README block, keyed by '<study> <machine label>'."""
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    outputs: Outputs = {}
    blocks: Dict[str, str] = {}
    for machine in manifest["machines"]:
        for name, study in STUDIES.items():
            if name not in machine:
                continue
            entry = machine[name]
            if entry.get("kind") != study.kind:
                raise PublishError(
                    f"{machine['label']} {name}: kind {entry.get('kind')!r} "
                    f"does not match the builder for {study.kind!r} rows"
                )
            files, block = study.build(root, machine)
            outputs.update(files)
            blocks[f"{name.replace('_', '-')} {machine['label']}"] = block
    return outputs, blocks


def splice(readme: str, blocks: Dict[str, str]) -> str:
    """Put each block between its BEGIN/END GENERATED markers. Every block needs a marker
    pair and every marker pair needs a block, so the README cannot drift from the rows."""
    seen = set()

    def fill(match: "re.Match[str]") -> str:
        block_id = match.group("id")
        if block_id not in blocks:
            raise PublishError(f"{README} has a generated block {block_id!r} that nothing builds")
        seen.add(block_id)
        return f"{match.group(1)}{blocks[block_id]}\n{match.group(4)}"

    text = BLOCK.sub(fill, readme)
    unplaced = sorted(set(blocks) - seen)
    if unplaced:
        raise PublishError(f"{README} has no markers for: {unplaced}")
    return text


def stale(root: Path, outputs: Outputs) -> List[str]:
    """Paths whose committed content differs from what the rows give now."""
    out = []
    for name, content in sorted(outputs.items()):
        path = root / name
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            out.append(name)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild README tables, reports and charts from raw rows")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if anything is out of date")
    parser.add_argument("--root", default=str(_REPO_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        outputs, blocks = build(root)
        outputs[README] = splice((root / README).read_text(encoding="utf-8"), blocks)
    except PublishError as exc:
        print(f"publish: {exc}", file=sys.stderr)
        return 2
    changed = stale(root, outputs)
    if args.check:
        for name in changed:
            print(f"out of date: {name}")
        print(f"publish --check: {len(outputs) - len(changed)} of {len(outputs)} files match the raw rows")
        return 1 if changed else 0
    for name in changed:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[name], encoding="utf-8")
        print(f"wrote {name}")
    print(f"publish: {len(outputs)} files built, {len(changed)} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
