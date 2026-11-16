#!/usr/bin/env python3
"""Summarize answer-quality rows: accuracy per setting and task, plus prompt-size checks.

Usage:
    python3 bench/quality_report.py results/mac3-media/quality-2026-11-16.jsonl
    python3 bench/quality_report.py results/*/quality-*.jsonl --out report-phase4/summary.md
"""

from __future__ import annotations

import argparse
import json
import sys
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


def accuracy(items: List[Dict[str, Any]]) -> Tuple[int, int]:
    scored = [r for r in items if "correct" in r]
    return sum(1 for r in scored if r["correct"]), len(scored)


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
        "| Setting | Task | Correct | Scored | Accuracy | Errors | Real/target prompt |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for (variant, task) in sorted(groups):
        items = groups[(variant, task)]
        correct, scored = accuracy(items)
        errors = sum(1 for r in items if r.get("status") == "error")
        pct = f"{correct / scored * 100:.1f}%" if scored else "-"
        fit = prompt_fit(items) or "-"
        lines.append(
            f"| {variant} | {task} | {correct} | {scored} | {pct} | {errors} | {fit} |"
        )
    empty = sum(1 for r in rows if not (r.get("content") or "").strip())
    lines += ["", f"Rows: {len(rows)}. Rows with empty answer text: {empty}."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize quality JSONL rows")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(f"missing: {missing}", file=sys.stderr)
        return 2

    rows = load_rows(paths)
    if not rows:
        print("no rows", file=sys.stderr)
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
