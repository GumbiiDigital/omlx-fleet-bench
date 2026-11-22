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
    LinePanel,
    LinePoint,
    LineSeries,
    bar_panels,
    interval_panels,
    line_panel,
    line_panels,
)
from bench.labels import (  # noqa: E402
    ARM_ALONE,
    ARM_HELPER,
    arm_label,
    arm_series,
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
# A wait longer than this is also given in minutes, so a reader can hold it in their head.
MINUTES_OVER_S = 120.0
# The most notes a reader page may put under one table or chart.
MAX_NOTES = 4

# Where each generated block goes: one line per study, and every block of that study lands on
# the page named here. The README keeps one block only, the headline, so a reader lands on the
# short answer first; the full tables live beside the question they answer.
PAGES: Dict[str, str] = {
    "headline": "README.md",
    "speed": "docs/speed.md",
    "speed_sweep": "docs/speed.md",
    "many_users": "docs/many-users.md",
    "kv_cache": "docs/memory.md",
    "quality": "docs/answer-quality.md",
    "helper_ready": "docs/helper-setup.md",
    "helper_layers": "docs/helper-setup.md",
}

# What a reader calls the two ways of starting a request in the helper-start study.
ROUND_TEXT = {"no wait": "Started at once", "wait": "Waited for the helper"}

BLOCK = re.compile(
    r"(<!-- BEGIN GENERATED: (?P<id>[^>]+?) -->\n)(?P<body>.*?)(<!-- END GENERATED: (?P=id) -->)",
    re.S,
)

Outputs = Dict[str, str]  # repo-relative path -> file content


class PublishError(Exception):
    """The manifest, the rows and the README do not fit together."""


@dataclass(frozen=True)
class Block:
    """One generated block: what it says, which page it belongs on, and its marker id."""

    id: str
    page: str
    body: str


def _display(machine: Dict[str, Any]) -> str:
    """The name a reader sees for this machine. Never the label the results files use."""
    name = machine.get("display_name")
    if not name:
        raise PublishError(f"{machine.get('label', '?')}: no display_name in {MANIFEST}")
    return str(name)


def duration(seconds: Optional[float]) -> str:
    """A wait in seconds, and over two minutes the same wait in minutes too."""
    if seconds is None:
        raise PublishError("a row has no wait for the first word to report")
    text = f"{seconds:.1f} s"
    return f"{text} ({seconds / 60:.1f} min)" if seconds > MINUTES_OVER_S else text


def _notes(notes: Sequence[str]) -> List[str]:
    """The notes under a table, as bullets, no more than the page is allowed to carry."""
    if len(notes) > MAX_NOTES:
        raise PublishError(f"a generated block asks for {len(notes)} notes; the limit is {MAX_NOTES}")
    return [f"- {note}" for note in notes]


def _runs_note(cells: Sequence["report.CellStats"]) -> str:
    """How many valid runs each figure rests on, read from the rows, not typed in."""
    counts = sorted({cell.n_valid for cell in cells})
    if len(counts) == 1:
        return f"Each figure is the mean of {counts[0]} valid runs."
    return "Valid runs per row of the table: " + ", ".join(str(count) for count in counts) + "."


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


def _charts_prefix(page: str) -> str:
    """The walk from a page to the charts folder: none at the root, one step up from docs/."""
    parent = Path(page).parent
    return "" if str(parent) == "." else "../" * len(parent.parts)


def _picture(chart: str, alt: str, page: str) -> List[str]:
    """The picture of a chart, dark and light, as a page at `page` path sees it.

    Every generated block that has a chart carries it, so a reader meets the picture beside the
    numbers it draws, and every chart file is shown by some page. The alt text says what the
    picture holds, in the same plain words as the rest of the page.
    """
    prefix = _charts_prefix(page)
    return [
        "<picture>",
        f'  <source media="(prefers-color-scheme: dark)" srcset="{prefix}charts/{chart}-dark.svg">',
        f'  <img alt="{alt}" src="{prefix}charts/{chart}-light.svg">',
        "</picture>",
        "",
    ]


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
    """The wait for the first word and the reading speed per setup and prompt size."""
    study, label, baseline = machine["speed"], machine["label"], machine["speed"]["baseline"]
    cells = _cells(_rows(root, study["files"]), label)
    by = _lookup(cells)
    variants = ordered_variants(c.variant for c in cells)
    sizes = sorted({c.size for c in cells})
    header = ["Setup"] + [size_label(s) for s in sizes]

    def ttft(variant: str, size: int) -> str:
        cell, base = by[(variant, size)], by[(baseline, size)]
        text = duration(cell.mean_ttft_s)
        return text if variant == baseline else f"{text} · {base.mean_ttft_s / cell.mean_ttft_s:.1f}×"

    ttft_rows = [[variant_label(v)] + [ttft(v, s) for s in sizes] for v in variants]
    tps_rows = [[variant_label(v)] + [f"{by[(v, s)].mean_tps:,.0f}" for s in sizes] for v in variants]
    noisy = [c for c in report.sort_cells(cells) if c.noisy]
    quiet = max(spread(c.valid_tps) for c in cells if not c.noisy) * 100
    spread_line = f"Repeat runs differed by at most {quiet:.1f}% in reading speed"
    if noisy:
        named = ", ".join(
            f"{variant_label(c.variant)} at {size_label(c.size)} ({spread(c.valid_tps) * 100:.1f}%)" for c in noisy
        )
        spread_line += f" except {named}"
    notes = [
        _runs_note(cells) + " Every run read its prompt with a cold cache (0 cached tokens).",
        spread_line + ".",
    ]
    if study.get("warm_rerun"):
        warm = report.sort_cells(_cells(_rows(root, study["warm_rerun"]), label))
        again = ", ".join(
            f"{variant_label(c.variant)} at {size_label(c.size)}: {c.mean_tps:,.0f} tokens/s "
            f"({by[(c.variant, c.size)].mean_tps:,.0f} in the first pass)"
            for c in warm
        )
        notes.append(f"Run again back to back, {warm[0].n_valid} runs each: {again}.")

    lines = [
        *_picture(
            f"{label}-ttft",
            f"Wait for the first word at 8K, 32K, 64K and 128K prompt tokens on {_display(machine)}, "
            "on the Mac alone and with each add-on",
            PAGES["speed"],
        ),
        f"### {_display(machine)}",
        "",
        f"The wait for the first word, in seconds. The second figure is how many times shorter "
        f"the wait is than on the {variant_label(baseline)}.",
        "",
        _table(header, ttft_rows),
        "",
        "Reading the prompt, in tokens per second:",
        "",
        _table(header, tps_rows),
        "",
        *_notes(notes),
    ]

    caption = Caption(
        title="Wait for the first word (seconds)",
        subtitle=[f"{_display(machine)} · {study['conditions']}"],
        footnotes=[
            f"Each panel has its own scale. “× faster” compares with {variant_label(baseline)} at the same prompt size."
        ],
    )
    panels = report.ttft_panels(cells, baseline)
    outputs = _charts(
        f"{label}-ttft",
        lambda theme: bar_panels(caption, panels, theme, axis_label="Wait for the first word (seconds)"),
    )
    outputs[f"reports/{label}/speed.md"] = report.summary_markdown(cells, f"{_display(machine)}: every speed row")
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

    header = ["KV cache"]
    for size in sizes:
        header += [f"{size_label(size)} peak memory", f"{size_label(size)} wait for the first word"]
    rows = []
    for variant in variants:
        row = [variant_label(variant)]
        for size in sizes:
            cell, base = by[(variant, size)], by[(baseline, size)]
            memory, wait = f"{cell.mean_peak_gb:.1f} GB", duration(cell.mean_ttft_s)
            if variant != baseline:
                memory += f" · {change(cell.mean_peak_gb, base.mean_peak_gb)}"
                wait += f" · {change(cell.mean_ttft_s, base.mean_ttft_s)}"
            row += [memory, wait]
        rows.append(row)
    worst = max(spread(c.valid_tps) for c in cells) * 100
    notes = [
        f"Peak memory is the most memory the whole run used, not the size of the KV cache alone.",
        f"{_runs_note(cells)} Repeat runs differed by at most {worst:.2f}% in reading speed.",
    ]
    lines = [
        *_picture(
            f"{label}-kv-memory",
            f"Peak memory of the whole run at 32K and 128K prompt tokens on {_display(machine)}, "
            "for each prompt memory setting",
            PAGES["kv_cache"],
        ),
        f"### {_display(machine)}",
        "",
        "The KV cache is the memory that holds the prompt. The second figure in a row is the "
        f"change against {variant_label(baseline)}.",
        "",
        _table(header, rows),
        "",
        *_notes(notes),
    ]

    caption = Caption(
        title="Peak memory by prompt memory setting (GB)",
        subtitle=[f"{_display(machine)} · {study['conditions']}"],
        footnotes=["Peak memory of the whole run, not the size of the KV cache alone. 1 GB = 2³⁰ bytes."],
    )
    panels = report.memory_panels(cells, baseline)
    outputs = _charts(
        f"{label}-kv-memory",
        lambda theme: bar_panels(caption, panels, theme, axis_label="Peak memory of the whole run (GB)"),
    )
    outputs[f"reports/{label}/kv-cache.md"] = report.summary_markdown(
        cells, f"{_display(machine)}: every KV cache row"
    )
    return outputs, "\n".join(lines)


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
    header.append("Answers that changed")
    table = []
    capped_by_setting = []
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
                f"{sum(m.lost for m in moved)} right answers became wrong, "
                f"{sum(m.gained for m in moved)} wrong answers became right "
                f"(of {sum(m.compared for m in moved)})"
            )
        cut_off = sum(quality_report.capped(groups[(variant, t)]) for t in tasks)
        capped_by_setting.append(f"{variant_label(variant)} {cut_off}")
        table.append(row)
    counted = sum(quality_report.capped(groups[(variant, t)]) for variant in variants for t in tasks)
    notes = [
        "Answers that ran out of tokens while the model was still thinking, and count as wrong: "
        f"{', '.join(capped_by_setting)} ({counted} in all).",
        "Every question was asked under every setting, at temperature 0, so the same question "
        "gets the same answer twice.",
    ]
    lines = [
        *_picture(
            f"{label}-quality",
            f"Share of answers right on the question sets on {_display(machine)}, for each setting, "
            "with a 95% range",
            PAGES["quality"],
        ),
        f"### {_display(machine)}",
        "",
        "Answers right, per question set and setting. The second figure in a row is the share "
        "right.",
        "",
        _table(header, table),
        "",
        *_notes(notes),
    ]

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
    footnotes = [
        "Dot: share of correct answers. Line: the 95% range for that share. The scale does not "
        "start at zero."
    ]
    for task in tasks:
        if task in charted:
            continue
        parts = sorted({scores[(v, task)] for v in variants})
        if len(parts) == 1:
            footnotes.append(f"{TASK_LABELS.get(task, task)}: {parts[0][0]} of {parts[0][1]} correct under every setting.")
    caption = Caption(
        title="Answers right by setting (%)",
        subtitle=[f"{_display(machine)} · {study['conditions']}"],
        footnotes=footnotes,
    )
    outputs = _charts(
        f"{label}-quality",
        lambda theme: interval_panels(
            caption,
            panels,
            theme,
            axis_min=axis_min,
            axis_max=100.0,
            ticks=ticks,
            tick_suffix="%",
            axis_label="Share of answers right (%)",
        ),
    )
    outputs[f"reports/{label}/quality.md"] = quality_report.write_summary(rows)
    return outputs, "\n".join(lines)


def build_speed_sweep(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """The wait for the first word at each prompt size, Mac alone against the helper.

    The same cells as the speed study, read one prompt size to a line: what changes as the
    prompt grows, not what changes between setups at one size.
    """
    study, label, baseline = machine["speed_sweep"], machine["label"], machine["speed_sweep"]["baseline"]
    cells = _cells(_rows(root, study["files"]), label)
    by = _lookup(cells)
    sizes = sorted({c.size for c in cells})
    helper = next((c.variant for c in cells if c.variant != baseline), None)
    if helper is None:
        raise PublishError(f"{label}: the prompt-size test needs a second setup to compare with {baseline!r}")

    rows = []
    for size in sizes:
        alone, helped = by[(baseline, size)].mean_ttft_s, by[(helper, size)].mean_ttft_s
        if alone is None or helped is None:
            raise PublishError(f"{label}: no wait for the first word at {size_label(size)}")
        rows.append([size_label(size), duration(alone), duration(helped), f"{alone / helped:.1f}×"])
    header = ["Prompt size", variant_label(baseline), variant_label(helper), "Faster by"]
    notes = [_runs_note(cells) + " Every run read its prompt with a cold cache (0 cached tokens)."]
    lines = [
        *_picture(
            f"{label}-ttft-sweep",
            f"Wait for the first word from 1K to 128K prompt tokens on {_display(machine)}, "
            "on the Mac alone and with the Spark helper",
            PAGES["speed_sweep"],
        ),
        f"### {_display(machine)}",
        "",
        "The wait for the first word at each prompt size, and how many times shorter it is with "
        "the helper.",
        "",
        _table(header, rows),
        "",
        *_notes(notes),
    ]

    caption = Caption(
        title="Wait for the first word by prompt size (seconds)",
        subtitle=[
            f"{_display(machine)} · {study['conditions']}",
            "Both axes multiply: 10 s to 100 s takes the same space as 100 s to 1,000 s, and 8K tokens "
            "to 80K the same as 80K to 800K.",
        ],
        footnotes=["One line per setup; every point carries its value."],
    )
    panel = report.ttft_lines(cells)
    outputs = _charts(f"{label}-ttft-sweep", lambda theme: line_panel(caption, panel, theme))
    outputs[f"reports/{label}/speed-sweep.md"] = report.summary_markdown(
        cells, f"{_display(machine)}: every prompt size"
    )
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
    """One sentence on the rows a flag marks not valid: why they are left out, and what they got.

    A row is marked from its start state alone, so the reason it is left out comes first and is
    kept apart from its time. The helper state at the start does not say who served the request: a
    request that goes out while the session is still starting can be read by the Mac alone or by
    the helper, and the measured wait is what tells them apart. A row served by the helper then
    reads as normal, which is why the sentence says where the helper was when the request went out.

    The reader meets these rows first as "do not count", so the sentence says why in plain words,
    then names the table line they sit on and the wait they got.
    """
    on_the_helper = flagged.at_helper_speed(alone)
    waits = f"{flagged.low_ttft_s:.2f} to {flagged.high_ttft_s:.2f} s"
    head = (
        f"These {flagged.requests} started before the helper was ready, so we do not count them. "
        f"They are the {path} / {arm} rows."
    )
    why = (
        " That mark comes from the start state alone, whatever wait the row got: a row that begins "
        "before the helper is up cannot be compared with the number a ready helper gives."
    )
    if on_the_helper == flagged.requests:
        got = (
            " Their time looks normal because the helper came up while the request was still in "
            f"flight, so they ran at helper speed ({waits})."
        )
    elif on_the_helper == 0:
        got = f" They ran at the speed of the Mac alone ({waits})."
    else:
        got = f" {on_the_helper} of {flagged.requests} ran at helper speed ({waits})."
    return head + why + got


def build_helper_ready(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """What the first request after a settings switch waited, one line per path and round.

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
        "When the prompt was sent",
        "Waited for the helper (s)",
        "Wait for the first word (s)",
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
                ROUND_TEXT.get(key[1], key[1]),
                f"{waits.mean_wait_s:.1f}",
                f"{waits.low_ttft_s:.2f} to {waits.high_ttft_s:.2f} s",
                f"{waits.at_helper_speed(alone)} of {waits.requests}",
            ]
        )

    counts = sorted({waits.requests for waits in groups.values()})
    count_text = (
        f"{counts[0]} requests in every line of the table."
        if len(counts) == 1
        else "Requests per line: " + ", ".join(str(count) for count in counts) + "."
    )
    states = "; ".join(
        f"{arm['path']}, {ROUND_TEXT.get(arm['arm'], arm['arm'])}: {groups[(arm['path'], arm['arm'])].state_text}"
        for arm in study["arms"]
    )
    notes = [
        count_text
        + " Each line is one request with the helper off and then one at 32K with the helper on, "
        "so every helper request starts straight after a switch.",
        f"The helper state at the start of the request: {states}.",
    ]
    not_ready = sum(1 for request in requests if "helper_ready_at_start" in request.failed)
    if not_ready:
        sentences = []
        for arm in study["arms"]:
            round_name = str(arm["arm"])
            waits = groups[(arm["path"], arm["arm"])]
            flagged = latency.Waits(
                [member for member in waits.members if "helper_ready_at_start" in member.failed]
            )
            if flagged.requests:
                sentences.append(
                    _not_valid_line(arm["path"], ROUND_TEXT.get(round_name, round_name), flagged, alone)
                )
        notes.append(" ".join(sentences))
    # The helper-off requests are there to force the switch; the cache and answer counts are the
    # helper-on ones, because those are the requests the table is about.
    notes.append(_reading_line(helped))

    lines = [
        f"### {_display(machine)}",
        "",
        "The wait for the first word of a request at 32K with the helper on, sent straight after a "
        "switch from helper off to helper on. One line per path and per way of starting.",
        "",
        _table(header, rows),
        "",
        *_notes(notes),
    ]

    outputs: Outputs = {
        f"reports/{label}/helper-ready.md": report.request_markdown(
            requests, f"{_display(machine)}: helper start, every request"
        )
    }
    return outputs, "\n".join(lines)


def build_helper_layers(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """The wait for the first word per helper layer count, at each prompt size, against the Mac alone."""
    study, label = machine["helper_layers"], machine["label"]
    requests = _requests(root, study, label)
    groups = latency.group_requests(requests, lambda request: (request.size, request.setting))
    sizes = sorted({request.size for request in requests})
    baseline = next((request.setting for request in requests if not request.helper_on), None)
    if baseline is None:
        raise PublishError(f"{label}: the layer study needs a request with the helper off to compare with")
    reference = min(size for size in sizes if (size, baseline) in groups)
    base = groups[(reference, baseline)].mean_ttft_s

    header = ["Setting"] + [f"{size_label(size)} wait for the first word" for size in sizes]
    header += ["Layers on the helper", f"Faster than the {setting_label(baseline)} at {size_label(reference)}"]
    rows = []
    for setting in ordered_settings(name for _, name in groups):
        row = [setting_label(setting)]
        for size in sizes:
            waits = groups.get((size, setting))
            row.append(
                "not run"
                if waits is None
                else f"{duration(waits.mean_ttft_s)}, {waits.low_ttft_s:.2f} to {waits.high_ttft_s:.2f} s"
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
        f"Each figure is the mean of {counts[0]} requests, with the smallest and largest after it."
        if len(counts) == 1
        else "Requests per line of the table: " + ", ".join(str(count) for count in counts) + "."
    )
    notes = [count_line, _reading_line(requests)]
    lines = [
        *_picture(
            f"{label}-helper-layers",
            f"Wait for the first word at 32K and 128K prompt tokens on {_display(machine)}, "
            "on the Mac alone and at each helper layer count",
            PAGES["helper_layers"],
        ),
        f"### {_display(machine)}",
        "",
        "The wait for the first word per helper layer count, and how many times faster than the "
        f"Mac alone at {size_label(reference)}. A layer is a slice of the model the helper holds.",
        "",
        _table(header, rows),
        "",
        *_notes(notes),
    ]

    caption = Caption(
        title="Wait for the first word by helper layer count (seconds)",
        subtitle=[f"{_display(machine)} · {study['conditions']}"],
        footnotes=[
            "Each panel has its own scale. “× faster” compares with the Mac alone at the same prompt size.",
            "A pinned count is the number of layers the helper was asked for; the table gives the number it held.",
        ],
    )
    panels = report.setting_panels(groups, baseline)
    outputs = _charts(
        f"{label}-helper-layers",
        lambda theme: bar_panels(caption, panels, theme, axis_label="Wait for the first word (seconds)"),
    )
    outputs[f"reports/{label}/helper-layers.md"] = report.request_markdown(
        requests, f"{_display(machine)}: helper layer count, every request"
    )
    return outputs, "\n".join(lines)


@dataclass(frozen=True)
class Study:
    """A published study: the shape of its rows, and the builder that reads them."""

    kind: str  # "speed", "quality" or "request": what one row of the study measures
    build: Callable[[Path, Dict[str, Any]], Tuple[Outputs, str]]


def _users_note(counts: Sequence[int]) -> str:
    """'1, 2, 4 and 8 users' — the user counts of the groups, in one phrase."""
    if len(counts) == 1:
        return f"{counts[0]} users"
    return ", ".join(str(count) for count in counts[:-1]) + f" and {counts[-1]} users"


def _groups_in_means(cells: Sequence["waves.WaveCell"], counts: Sequence[int]) -> str:
    """One sentence on how many groups each mean rests on, read from the cells themselves.

    A cell whose every group broke has no mean, so the sentence then gives a range that starts at
    zero and points the reader at the report for the count of each cell.
    """
    used = sorted({cell.waves_used for cell in cells})
    if len(used) == 1 and used[0] > 0:
        return f"Mean of {used[0]} groups per case, at {_users_note(counts)} per group."
    if len(used) == 1:
        return "No cell has a fully valid group, so every mean in the table is `-`."
    return (
        f"A mean rests on {used[0]} to {used[-1]} groups per case, at {_users_note(counts)} per group; "
        "the report gives the count for each cell."
    )


def _wave_text(cell: "waves.WaveCell") -> str:
    """The mean time of a whole group, or '-' when no group of the cell is fully valid."""
    return duration(cell.mean_wall_s) if cell.has_valid_wave else "-"


def _speed_up_text(cell: "waves.WaveCell", base: "waves.WaveCell", arm: str, baseline: str) -> str:
    """How many times shorter this group is than the Mac-alone group of the same cell.

    Both sides need a group that survived its checks: a missing figure on either side leaves the
    speed-up unknown, which is not the same as a speed-up of one.
    """
    if arm == baseline:
        return "baseline"
    if not (cell.has_valid_wave and base.has_valid_wave):
        return "-"
    return f"{waves.comparison(cell, base):.2f}×"


def _wave_cells(rows: List[Dict[str, Any]], label: str) -> List["waves.WaveCell"]:
    """Every cell of a many-users study, checked to cover each prompt size, user count and setup."""
    cells = waves.sort_cells(list(waves.cells(rows).values()))
    if not cells:
        raise PublishError(f"{label}: no many-users request for this machine")
    arms = ordered_arms(cell.arm for cell in cells)
    if len(arms) < 2:
        raise PublishError(f"{label}: the study needs a second setup to compare with {arms[0]!r}")
    wanted = {
        (size, users, arm)
        for size in {cell.size for cell in cells}
        for users in {cell.users for cell in cells}
        for arm in arms
    }
    missing = sorted(wanted - {(cell.size, cell.users, cell.arm) for cell in cells})
    if missing:
        raise PublishError(
            f"{label}: cells without a group: "
            + ", ".join(f"{size_label(size)} / {users} users / {arm_label(arm)}" for size, users, arm in missing)
        )
    return cells


def build_many_users(root: Path, machine: Dict[str, Any]) -> Tuple[Outputs, str]:
    """Time for a group of many requests at once, the Mac alone against the helper.

    A many-users row is one request of a group: N requests that begin at one moment. The cell comes
    from the row's own fields (prompt size, user count, whether the helper was on, which group), so
    no setup name is typed in. The figure is the study's own: the time from the first request of
    the group to its last reply.
    """
    study, label = machine["many_users"], machine["label"]
    cells = _wave_cells([row for row in _rows(root, study["files"]) if row.get("machine") == label], label)
    arms = ordered_arms(cell.arm for cell in cells)
    baseline = arms[0]
    by = {(cell.size, cell.users, cell.arm): cell for cell in cells}
    sizes = sorted({cell.size for cell in cells})
    counts = sorted({cell.users for cell in cells})

    header = ["Prompt size", "Users"] + [arm_label(arm) for arm in arms] + ["Faster by"]
    rows = []
    for size in sizes:
        for users in counts:
            base = by[(size, users, baseline)]
            row = [size_label(size), str(users)]
            row += [_wave_text(by[(size, users, arm)]) for arm in arms]
            row.append(_speed_up_text(by[(size, users, arms[-1])], base, arms[-1], baseline))
            rows.append(row)

    notes = [
        _groups_in_means(cells, counts),
        "If one request in a group fails our checks, we leave out the whole group.",
    ]
    members = [member for cell in cells for member in cell.members]
    marked = waves.failed_marks(members)
    if marked:
        counts_text = ", ".join(f"{count} · {name}" for name, count in sorted(marked.items()))
        notes.append(f"Requests marked not valid by a check, kept in their group's count and out of its means: {counts_text}.")
    notes.append(waves.reading_line(members))

    lines = [
        *_picture(
            f"{label}-many-users",
            f"Time for a whole group of requests to finish at 4K and 32K prompt tokens on "
            f"{_display(machine)}, on the Mac alone and with the Spark helper",
            PAGES["many_users"],
        ),
        f"### {_display(machine)}",
        "",
        "Time for a whole group of requests to finish, at each prompt size and user count. A group "
        "is its user count of requests sent at the same moment. Lower is better.",
        "",
        _table(header, rows),
        "",
        *_notes(notes),
    ]

    outputs: Outputs = {
        f"reports/{label}/many-users.md": report.wave_markdown(
            cells, f"{_display(machine)}: many users, every group"
        )
    }
    plottable = [cell for cell in cells if cell.has_valid_wave]
    if plottable:
        caption = Caption(
            title="Time for a whole group of requests to finish (seconds)",
            subtitle=[
                f"{_display(machine)} · {study['conditions']}",
                "Both axes multiply: 10 s to 100 s takes the same space as 100 s to 1,000 s, and 1 user "
                "to 4 the same as 4 to 16.",
            ],
            footnotes=[
                "Every point carries its value.",
                "A group is its user count of requests sent at the same moment. Lower is better.",
            ],
        )
        panels = report.wave_lines(plottable)
        outputs.update(
            _charts(
                f"{label}-many-users",
                lambda theme: line_panels(caption, panels, theme),
            )
        )
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


@dataclass(frozen=True)
class Headline:
    """One machine's line of the front-door picture: the Mac alone against the Mac with its helper."""

    display: str
    sizes: Sequence[int]
    alone: Sequence[float]
    helped: Sequence[float]


def _headline_rows(root: Path, machine: Dict[str, Any]) -> Optional[Headline]:
    """The two setups of one machine's speed study, at each prompt size both of them ran.

    The helper is the Spark setup of that study. A machine whose study has no second setup has no
    line to draw, so it is left out rather than given a made-up comparison.
    """
    if "speed" not in machine:
        return None
    study, label = machine["speed"], machine["label"]
    try:
        cells = _cells(_rows(root, study["files"]), label)
    except PublishError:
        return None
    baseline = study["baseline"]
    helper = "spark" if any(c.variant == "spark" for c in cells) else None
    if helper is None:
        others = [c.variant for c in cells if c.variant != baseline]
        helper = ordered_variants(others)[0] if others else None
    if helper is None:
        return None
    by = _lookup(cells)
    sizes, alone, helped_waits = [], [], []
    for size in sorted({c.size for c in cells}):
        base_cell, helper_cell = by.get((baseline, size)), by.get((helper, size))
        if base_cell is None or helper_cell is None:
            continue
        if base_cell.mean_ttft_s is None or helper_cell.mean_ttft_s is None:
            continue
        sizes.append(size)
        alone.append(base_cell.mean_ttft_s)
        helped_waits.append(helper_cell.mean_ttft_s)
    if not sizes:
        return None
    return Headline(display=_display(machine), sizes=sizes, alone=alone, helped=helped_waits)


def build_headline(root: Path, manifest: Dict[str, Any]) -> Optional[Tuple[Outputs, str]]:
    """The one block the README carries: every Mac, alone and with its helper, on one chart.

    The numbers are the same cells the speed blocks read, so the front door cannot drift from the
    page behind it. Nothing here is typed: the prompt sizes, the waits and the speed-ups all come
    from the rows.
    """
    lines = [entry for entry in (_headline_rows(root, machine) for machine in manifest["machines"]) if entry]
    if not lines:
        return None
    sizes = sorted({size for entry in lines for size in entry.sizes})
    waits = [value for entry in lines for value in (*entry.alone, *entry.helped)]
    colours = arm_series([ARM_ALONE, ARM_HELPER])
    panels = [
        LinePanel(
            title=entry.display,
            x_min=sizes[0],
            x_max=sizes[-1],
            y_min=min(waits),
            y_max=max(waits),
            x_ticks=[(size, size_label(size)) for size in sizes],
            y_ticks=[(tick, f"{tick:g} s") for tick in report.log_ticks(min(waits), max(waits))],
            series=[
                LineSeries(
                    arm_label(ARM_ALONE),
                    colours[ARM_ALONE],
                    [
                        LinePoint(size, value, size_label(size), f"{value:.1f} s")
                        for size, value in zip(entry.sizes, entry.alone)
                    ],
                ),
                LineSeries(
                    arm_label(ARM_HELPER),
                    colours[ARM_HELPER],
                    [
                        LinePoint(size, value, size_label(size), f"{value:.1f} s")
                        for size, value in zip(entry.sizes, entry.helped)
                    ],
                ),
            ],
            x_label="Prompt size (tokens)",
            y_label="Wait for the first word (s)",
        )
        for entry in lines
    ]
    caption = Caption(
        title="Wait for the first word, Mac alone and with the Spark helper (seconds)",
        subtitle=[
            " · ".join(entry.display for entry in lines),
            "Mean of the valid runs, cold cache.",
            "Both axes multiply: 10 s to 100 s takes the same space as 100 s to 1,000 s, and 8K tokens "
            "to 80K the same as 80K to 800K.",
        ],
        footnotes=[
            "Every point carries its value.",
            "The helper is the DGX Spark that reads long prompts for the Mac. Lower is better.",
        ],
    )
    outputs = _charts("headline", lambda theme: line_panels(caption, panels, theme))

    header = ["Prompt size", arm_label(ARM_ALONE), arm_label(ARM_HELPER), "Faster by"]
    body = [
        "<picture>",
        '  <source media="(prefers-color-scheme: dark)" srcset="charts/headline-dark.svg">',
        f'  <img alt="Wait for the first word at {", ".join(size_label(size) for size in sizes)} prompt '
        f'tokens on {len(lines)} Macs, alone and with the Spark helper" src="charts/headline-light.svg">',
        "</picture>",
        "",
    ]
    for entry in lines:
        rows = [
            [size_label(size), duration(alone), duration(helped), f"{alone / helped:.1f}×"]
            for size, alone, helped in zip(entry.sizes, entry.alone, entry.helped)
        ]
        body += [f"#### {entry.display}", "", _table(header, rows), ""]
    notes = [
        "Mac alone is the Mac on its own; Mac + Spark is the same Mac with the Spark helper reading "
        "the prompt at the same time.",
        "Every figure is the mean of the valid runs of that Mac's speed study, each run with a cold "
        "cache (the server held none of the prompt).",
    ]
    body += _notes(notes)
    return outputs, "\n".join(body)


def build(root: Path) -> Tuple[Outputs, Dict[str, Block]]:
    """Every generated file, and every generated block keyed by its marker id."""
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    outputs: Outputs = {}
    blocks: Dict[str, Block] = {}
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
            files, body = study.build(root, machine)
            outputs.update(files)
            block_id = f"{name.replace('_', '-')} {machine['label']}"
            blocks[block_id] = Block(block_id, PAGES[name], body)
    headline = build_headline(root, manifest)
    if headline is not None:
        files, body = headline
        outputs.update(files)
        blocks["headline"] = Block("headline", PAGES["headline"], body)
    return outputs, blocks


def splice(text: str, blocks: Dict[str, str], page: str = README) -> str:
    """Put each block between its BEGIN/END GENERATED markers. Every block needs a marker
    pair and every marker pair needs a block, so a page cannot drift from the rows."""
    seen = set()

    def fill(match: "re.Match[str]") -> str:
        block_id = match.group("id")
        if block_id not in blocks:
            raise PublishError(f"{page} has a generated block {block_id!r} that nothing builds")
        seen.add(block_id)
        return f"{match.group(1)}{blocks[block_id]}\n{match.group(4)}"

    spliced = BLOCK.sub(fill, text)
    unplaced = sorted(set(blocks) - seen)
    if unplaced:
        raise PublishError(f"{page} has no markers for: {unplaced}")
    return spliced


def page_bodies(blocks: Dict[str, Block]) -> Dict[str, Dict[str, str]]:
    """The blocks grouped by the page they belong on, in the order PAGES names the pages."""
    pages: Dict[str, Dict[str, str]] = {}
    for block in blocks.values():
        pages.setdefault(block.page, {})[block.id] = block.body
    return pages


# Every page a reader lands on, whether or not the layout gives it a block today. A marker that
# turns up on one of these and is not in PAGES for its block is a fault, not something to skip.
READER_PAGE_PATTERNS = ("README.md", "docs/*.md")


def reader_pages(root: Path) -> List[str]:
    """Every page that may hold a generated block: the layout's pages first, then the rest."""
    names = list(dict.fromkeys(PAGES.values()))
    for pattern in READER_PAGE_PATTERNS:
        for path in sorted(root.glob(pattern)):
            name = path.relative_to(root).as_posix()
            if name not in names:
                names.append(name)
    return names


def splice_pages(root: Path, blocks: Dict[str, Block]) -> Outputs:
    """Every reader page with its blocks in place, and a fault for a marker on the wrong page.

    A page the layout does not name gets no block, so a marker there has nothing to fill it and
    raises. That is the point: a generated block cannot sit on a page the layout says it is not on.
    """
    pages = page_bodies(blocks)
    written: Outputs = {}
    for page in reader_pages(root):
        path = root / page
        if not path.is_file():
            if page in pages:
                raise PublishError(f"{page} is missing, and its generated blocks have nowhere to go")
            continue
        text = path.read_text(encoding="utf-8")
        if page not in pages and "BEGIN GENERATED" not in text:
            continue  # a page with no block and no marker is hand text only; leave it alone
        written[page] = splice(text, pages.get(page, {}), page)
    return written


def stale(root: Path, outputs: Outputs) -> List[str]:
    """Paths whose committed content differs from what the rows give now."""
    out = []
    for name, content in sorted(outputs.items()):
        path = root / name
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            out.append(name)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild the reader pages, reports and charts from raw rows")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if anything is out of date")
    parser.add_argument("--root", default=str(_REPO_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        outputs, blocks = build(root)
        outputs.update(splice_pages(root, blocks))
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
