#!/usr/bin/env python3
"""Summarize answer-quality rows: accuracy per setting and task, plus prompt-size checks.

Usage:
    python3 bench/quality_report.py results/my-mac/quality-DATE.jsonl
    python3 bench/quality_report.py base.jsonl --replace reask.jsonl --out report/quality.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_rows(paths: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def group(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    out: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        out.setdefault((row.get("variant", ""), row.get("task", "")), []).append(row)
    return out


def row_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    """Identity of one answer: which setting, which task, which sample."""
    return (str(row.get("variant", "")), str(row.get("task", "")), str(row.get("sample_id", "")))


def apply_replacements(
    base_rows: List[Dict[str, Any]], new_rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Put re-asked answers in the place of the rows they answer again.

    A new row replaces the base row with the same key and keeps its position. A key
    that is not in the base is an error: it means the files do not belong together,
    and a silent drop would hide that.
    """
    by_key = {row_key(row): row for row in new_rows}
    known = {row_key(row) for row in base_rows}
    unknown = sorted(set(by_key) - known)
    if unknown:
        raise ValueError(f"replacement key not in base rows: {unknown[0]}")
    if not by_key:
        return list(base_rows)
    return [by_key.get(row_key(row), row) for row in base_rows]


def accuracy(items: List[Dict[str, Any]]) -> Tuple[int, int]:
    scored = [r for r in items if "correct" in r]
    return sum(1 for r in scored if r["correct"]), len(scored)


@dataclass(frozen=True)
class AnswerChanges:
    """How one setting's answers differ from the baseline setting's, sample by sample."""

    compared: int
    gained: int  # baseline wrong, this setting right
    lost: int  # baseline right, this setting wrong
    different_text: int  # the answer text is not identical


def changes_against(
    rows: List[Dict[str, Any]], baseline: str
) -> Dict[Tuple[str, str], AnswerChanges]:
    """Compare every setting with `baseline` on the samples both answered.

    Accuracy alone can hide movement: ten answers lost and ten gained is the same score.
    The paired counts show how many answers a setting really moved.
    """
    by_key = {row_key(row): row for row in rows if "correct" in row}
    out: Dict[Tuple[str, str], AnswerChanges] = {}
    for (variant, task), items in group(rows).items():
        if variant == baseline:
            continue
        compared = gained = lost = different = 0
        for row in items:
            base = by_key.get((baseline, task, str(row.get("sample_id", ""))))
            if base is None or "correct" not in row:
                continue
            compared += 1
            gained += bool(row["correct"]) and not base["correct"]
            lost += bool(base["correct"]) and not row["correct"]
            different += (row.get("content") or "") != (base.get("content") or "")
        out[(variant, task)] = AnswerChanges(compared, gained, lost, different)
    return out


def capped(items: List[Dict[str, Any]]) -> int:
    """Answers cut off by the token cap (finish_reason "length")."""
    return sum(1 for r in items if r.get("finish_reason") == "length")


def prompt_fit(items: List[Dict[str, Any]]) -> Optional[str]:
    """Passkey rows carry a target token count; report the real prompt size against it."""
    fits = []
    for row in items:
        target = row.get("target_tokens")
        actual = (row.get("usage") or {}).get("prompt_tokens")
        if target and actual:
            fits.append(actual / target)
    if not fits:
        return None
    return f"{min(fits) * 100:.0f}-{max(fits) * 100:.0f}%"


def write_summary(rows: List[Dict[str, Any]]) -> str:
    groups = group(rows)
    lines = [
        "# Answer quality summary",
        "",
        "| Setting | Task | Correct | Scored | Accuracy | Errors | Real/target prompt | Capped |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for (variant, task) in sorted(groups):
        items = groups[(variant, task)]
        correct, scored = accuracy(items)
        errors = sum(1 for r in items if r.get("status") == "error")
        n_capped = capped(items)
        pct = f"{correct / scored * 100:.1f}%" if scored else "-"
        fit = prompt_fit(items) or "-"
        lines.append(
            f"| {variant} | {task} | {correct} | {scored} | {pct} | {errors} | {fit} | {n_capped} |"
        )
    empty = sum(1 for r in rows if not (r.get("content") or "").strip())
    lines += ["", f"Rows: {len(rows)}. Rows with empty answer text: {empty}."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize quality JSONL rows")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--replace",
        action="append",
        default=None,
        metavar="FILE",
        help="rows in FILE stand in for base rows with the same setting, task and sample (repeatable)",
    )
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths]
    replace_paths = [Path(p) for p in (args.replace or [])]
    missing = [str(p) for p in paths + replace_paths if not p.exists()]
    if missing:
        print(f"missing: {missing}", file=sys.stderr)
        return 2

    rows = load_rows(paths)
    if not rows:
        print("no rows", file=sys.stderr)
        return 2
    if replace_paths:
        try:
            rows = apply_replacements(rows, load_rows(replace_paths))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    summary = write_summary(rows)
    print(summary)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(summary, encoding="utf-8")
    # exit 0 only when nothing errored and every group produced scored rows
    errors = sum(1 for r in rows if r.get("status") == "error")
    unscored = [key for key, items in group(rows).items() if not accuracy(items)[1]]
    return 0 if errors == 0 and not unscored else 1


if __name__ == "__main__":
    raise SystemExit(main())
