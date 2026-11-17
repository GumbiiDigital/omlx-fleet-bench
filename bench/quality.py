#!/usr/bin/env python3
"""Run answer-quality checks against oMLX settings and write one JSONL row per request.

Does a setting (ANE prefill, Spark helper, KV compression) change what the model answers?

Usage:
    python3 bench/quality.py --matrix matrices/quality.json --base-url http://127.0.0.1:8004 \
        --settings ~/.omlx/settings.json --helper-node NODE_ID --machine my-mac \
        --out results/my-mac/quality-DATE.jsonl

The runner sets the matrix settings on the model (and restores them afterwards the same
way the benchmark runner does), then sends chat requests. Nothing is uploaded anywhere:
the chat path has no leaderboard upload.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bench.chat import ChatClient, ChatError  # noqa: E402
from bench.client import OMLXClient, load_api_key  # noqa: E402
from bench.matrix import SETTING_FIELDS, _variant_flags, settings_fields_touched  # noqa: E402
from bench.qa import (  # noqa: E402
    approximate_tokens,
    build_passkey_prompt,
    format_mmlu_prompt,
    gsm8k_prompt,
    prompt_messages,
    score_gsm8k,
    score_mmlu,
    score_passkey,
)

logger = logging.getLogger("bench.quality")

PROGRESS_EVERY = 25
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
DEFAULT_READY_TIMEOUT_S = 600.0


class ConsecutiveFailureGuard:
    """Stop a run after N identical errors in a row.

    oMLX can refuse every request the same way (409 "busy; unload pending") while the
    server still answers HTTP, so a run needs a limit on repeated identical failures
    instead of writing thousands of error rows. A different error, or a success,
    restarts the count.
    """

    def __init__(self, limit: int = DEFAULT_MAX_CONSECUTIVE_FAILURES) -> None:
        if limit < 1:
            raise ValueError("max consecutive failures must be 1 or more")
        self.limit = limit
        self._last_error: Optional[str] = None
        self._count = 0

    @property
    def count(self) -> int:
        """How many identical failures have happened in a row."""
        return self._count

    def record_success(self) -> None:
        self._last_error = None
        self._count = 0

    def record_failure(self, error: str) -> bool:
        """Count one failure; return True when the run must stop."""
        if error == self._last_error:
            self._count += 1
        else:
            self._last_error = error
            self._count = 1
        return self._count >= self.limit


@dataclass
class QualityVariant:
    """One setting under test."""

    name: str
    helper_on: bool
    ane_on: bool
    settings_patch: Dict[str, Any] = field(default_factory=dict)

    def merge_settings(self, base: Dict[str, Any], helper_node_id: str) -> Dict[str, Any]:
        merged = dict(base)
        merged.update(self.settings_patch)
        merged["qwen35_ane_prefill_enabled"] = self.ane_on
        merged["prefill_helper_node_id"] = helper_node_id if self.helper_on else ""
        return merged


@dataclass
class QualityUnit:
    """One request to send."""

    variant: QualityVariant
    task: str
    sample_id: str
    max_tokens: int
    messages: List[Dict[str, str]]
    expected: Any
    target_tokens: Optional[int] = None
    prompt_chars: int = 0


def load_quality_matrix(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("model", "variants", "tasks"):
        if key not in data:
            raise ValueError(f"quality matrix needs '{key}'")
    return data


def load_variants(matrix: Dict[str, Any], only: Optional[Sequence[str]] = None) -> List[QualityVariant]:
    wanted = set(only) if only else None
    variants: List[QualityVariant] = []
    for raw in matrix["variants"]:
        name = raw["name"]
        if wanted is not None and name not in wanted:
            continue
        helper_on, ane_on = _variant_flags(raw)
        patch = {k: v for k, v in (raw.get("settings") or {}).items() if k in SETTING_FIELDS}
        variants.append(QualityVariant(name=name, helper_on=helper_on, ane_on=ane_on, settings_patch=patch))
    return variants


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def unit_key(variant: str, task: str, sample_id: str) -> Tuple[str, str, str]:
    """Identity of one answer: which setting, which task, which sample."""
    return (variant, task, sample_id)


def capped_keys(rows: Iterable[Dict[str, Any]]) -> Set[Tuple[str, str, str]]:
    """Keys of answers that ran out of tokens while still thinking.

    finish_reason "length" means the cap cut the reply off, so the answer was never
    given. Those are the ones worth re-asking with a bigger cap.
    """
    return {
        unit_key(str(row.get("variant", "")), str(row.get("task", "")), str(row.get("sample_id", "")))
        for row in rows
        if row.get("finish_reason") == "length"
    }


def select_units(
    units: Sequence[QualityUnit], keys: Set[Tuple[str, str, str]]
) -> List[QualityUnit]:
    """Keep only units whose key is wanted, in the order they were built."""
    return [unit for unit in units if unit_key(unit.variant.name, unit.task, unit.sample_id) in keys]


def scale_max_tokens(units: Sequence[QualityUnit], scale: int) -> List[QualityUnit]:
    """Multiply every unit's token cap by scale, keeping order."""
    if scale < 1:
        raise ValueError("max tokens scale must be 1 or more")
    if scale == 1:
        return list(units)
    return [replace(unit, max_tokens=unit.max_tokens * scale) for unit in units]


def _passkey_units(
    task: Dict[str, Any],
    needles: Sequence[str],
    *,
    variant_name: str = "",
    cache_bust: bool = True,
) -> Iterable[Dict[str, Any]]:
    """One unit per size and sample. The tag line is unique per variant and sample so the
    server cannot answer a later variant from the prompt cache of an earlier one."""
    for size in [int(s) for s in task["sizes"]]:
        for index in range(int(task.get("samples_per_size", 1))):
            needle = needles[index % len(needles)]
            sample_id = f"passkey-{size}-{index}"
            tag = f"{variant_name}/{sample_id}" if cache_bust and variant_name else ""
            text = build_passkey_prompt(size, needle, cache_tag=tag)
            yield {
                "sample_id": sample_id,
                "size": size,
                "needle": needle,
                "prompt": text,
                "max_tokens": int(task.get("max_tokens", 64)),
            }


def build_units(
    matrix: Dict[str, Any],
    variants: Sequence[QualityVariant],
    *,
    only_tasks: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> List[QualityUnit]:
    """Expand matrix into units, variant by variant.

    Variant-major order keeps the settings stable for a whole block, so the server is
    not asked to rebuild its cache layout between single requests.
    """
    wanted = set(only_tasks) if only_tasks else None
    units: List[QualityUnit] = []
    for variant in variants:
        for task in matrix["tasks"]:
            name = task["name"]
            if wanted is not None and name not in wanted:
                continue
            if name in ("gsm8k", "mmlu"):
                rows = read_jsonl((_REPO_ROOT / task["data"]).resolve())
                if limit:
                    rows = rows[:limit]
                for row in rows:
                    if name == "gsm8k":
                        prompt = gsm8k_prompt(row["question"])
                        expected = row["answer"]
                    else:
                        prompt = format_mmlu_prompt(
                            row["question"], row["choices"], row.get("subject", "")
                        )
                        expected = int(row["answer"])
                    units.append(
                        QualityUnit(
                            variant=variant,
                            task=name,
                            sample_id=str(row.get("id") or ""),
                            max_tokens=int(task.get("max_tokens", 1024)),
                            messages=prompt_messages(prompt),
                            expected=expected,
                            prompt_chars=len(prompt),
                        )
                    )
            elif name == "passkey":
                needles = task.get("needles") or ["4829157"]
                cache_bust = bool(task.get("cache_bust", True))
                count = 0
                for unit_row in _passkey_units(
                    task, needles, variant_name=variant.name, cache_bust=cache_bust
                ):
                    if limit and count >= limit:
                        break
                    count += 1
                    units.append(
                        QualityUnit(
                            variant=variant,
                            task=name,
                            sample_id=str(unit_row["sample_id"]),
                            max_tokens=int(unit_row["max_tokens"]),
                            messages=prompt_messages(str(unit_row["prompt"])),
                            expected=str(unit_row["needle"]),
                            target_tokens=int(unit_row["size"]),
                            prompt_chars=len(str(unit_row["prompt"])),
                        )
                    )
            else:
                raise ValueError(f"unknown task '{name}'")
    return units


def score_unit(unit: QualityUnit, content: str) -> Dict[str, Any]:
    if unit.task == "gsm8k":
        return score_gsm8k(content, str(unit.expected))
    if unit.task == "mmlu":
        return score_mmlu(content, int(unit.expected))
    if unit.task == "passkey":
        return score_passkey(content, str(unit.expected))
    raise ValueError(f"unknown task '{unit.task}'")


def append_row(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


@dataclass
class RunContext:
    """Fixed facts that every row of one run shares."""

    machine: str
    matrix_path: str
    model: str
    fields: List[str]
    out_path: Path
    total_units: int


def build_row(
    context: RunContext,
    variant: QualityVariant,
    unit: QualityUnit,
    desired: Dict[str, Any],
    original: Dict[str, Any],
) -> Dict[str, Any]:
    """Row skeleton for one request, before the reply is known."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "machine": context.machine,
        "matrix": context.matrix_path,
        "model": context.model,
        "variant": variant.name,
        "helper_on": variant.helper_on,
        "ane_on": variant.ane_on,
        "task": unit.task,
        "sample_id": unit.sample_id,
        "max_tokens": unit.max_tokens,
        "target_tokens": unit.target_tokens,
        "prompt_chars": unit.prompt_chars,
        "approximate_prompt_tokens": (
            approximate_tokens(unit.messages[-1]["content"]) if unit.target_tokens else None
        ),
        "desired_settings": {k: desired.get(k) for k in context.fields},
        "settings_before": original,
        "expected": unit.expected,
    }


def send_block(
    chat: ChatClient,
    context: RunContext,
    variant: QualityVariant,
    units: Sequence[QualityUnit],
    desired: Dict[str, Any],
    original: Dict[str, Any],
    guard: ConsecutiveFailureGuard,
    sent_before: int,
) -> Tuple[int, bool]:
    """Send one variant's units. Return (rows written, stopped early)."""
    sent = 0
    for unit in units:
        if unit.variant.name != variant.name:
            continue
        row = build_row(context, variant, unit, desired, original)
        try:
            reply = chat.chat(context.model, unit.messages, max_tokens=unit.max_tokens)
        except ChatError as exc:
            logger.exception("Request failed for %s", unit.sample_id)
            row.update({"status": "error", "error": str(exc), "correct": False})
            append_row(context.out_path, row)
            sent += 1
            if guard.record_failure(str(exc)):
                return sent, True
            continue
        guard.record_success()
        score = score_unit(unit, reply["content"])
        row.update(
            {
                "status": "completed",
                "finish_reason": reply["finish_reason"],
                "content": reply["content"],
                "reasoning_chars": len(reply["reasoning"]),
                "usage": reply["usage"],
                "server_timing": reply["server_timing"],
                "latency_s": reply["latency_s"],
                **score,
            }
        )
        if not reply["content"].strip():
            row["note"] = "no_answer_text"
        append_row(context.out_path, row)
        sent += 1
        if (sent_before + sent) % PROGRESS_EVERY == 0:
            logger.info("Sent %d/%d requests", sent_before + sent, context.total_units)
    return sent, False


def run(args: argparse.Namespace) -> int:
    matrix = load_quality_matrix(args.matrix)
    base_settings = dict(matrix.get("base_settings") or {})
    variants = load_variants(matrix, args.only_variants and args.only_variants.split(","))
    units = build_units(
        matrix,
        variants,
        only_tasks=args.only_tasks.split(",") if args.only_tasks else None,
        limit=args.limit,
    )

    if args.retry_capped:
        capped_rows: List[Dict[str, Any]] = []
        for path in args.retry_capped:
            capped_rows.extend(read_jsonl(Path(path)))
        keys = capped_keys(capped_rows)
        units = select_units(units, keys)
        logger.info("Retry: %d capped answers found, %d units selected", len(keys), len(units))
        if not units:
            print("no capped answer in those files matches this matrix", file=sys.stderr)
            return 2

    units = scale_max_tokens(units, args.max_tokens_scale)

    if args.dry_run:
        for unit in units[:20]:
            print(
                f"{unit.variant.name:9s} {unit.task:8s} {unit.sample_id:24s} "
                f"max_tokens={unit.max_tokens} target_tokens={unit.target_tokens or '-'} "
                f"prompt_chars={unit.prompt_chars}"
            )
        counts: Dict[str, int] = {}
        for unit in units:
            counts[f"{unit.variant.name}:{unit.task}"] = counts.get(f"{unit.variant.name}:{unit.task}", 0) + 1
        print(f"Total requests: {len(units)}")
        for key in sorted(counts):
            print(f"  {key}: {counts[key]}")
        return 0

    guard = ConsecutiveFailureGuard(args.max_consecutive_failures)
    api_key = load_api_key(args.settings)
    admin = OMLXClient(args.base_url, api_key)
    admin.login()
    chat = ChatClient(args.base_url, api_key, timeout_s=args.timeout)
    fields = settings_fields_touched([], base_settings)
    out_path = Path(args.out)
    context = RunContext(
        machine=args.machine,
        matrix_path=str(Path(args.matrix)),
        model=matrix["model"],
        fields=fields,
        out_path=out_path,
        total_units=len(units),
    )
    sent = 0

    with admin.preserved_settings(matrix["model"], fields) as original:
        for variant in variants:
            desired = variant.merge_settings(base_settings, args.helper_node or "")
            admin.apply_settings(matrix["model"], desired, fields)
            try:
                chat.wait_until_ready(matrix["model"], timeout_s=args.ready_timeout)
            except ChatError as exc:
                logger.error("Model not ready for variant %s: %s", variant.name, exc)
                logger.error("Run stopped after %d rows; settings are restored", sent)
                return 1
            block_sent, stopped = send_block(
                chat, context, variant, units, desired, original, guard, sent
            )
            sent += block_sent
            if stopped:
                logger.error(
                    "Stopped after %d identical failures in a row (variant %s); wrote %d rows",
                    guard.count,
                    variant.name,
                    sent,
                )
                return 1
    logger.info("Wrote %d rows to %s", sent, out_path)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="oMLX answer-quality runner")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--helper-node", default="")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--only-variants", default=None, help="comma separated variant names")
    parser.add_argument("--only-tasks", default=None, help="comma separated task names")
    parser.add_argument("--limit", type=int, default=None, help="first N samples per task")
    parser.add_argument(
        "--retry-capped",
        action="append",
        default=None,
        metavar="FILE",
        help="re-ask only the answers in FILE that stopped at the token cap (repeatable)",
    )
    parser.add_argument(
        "--max-tokens-scale",
        type=int,
        default=1,
        metavar="N",
        help="multiply every request's token cap by N (default 1)",
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=DEFAULT_MAX_CONSECUTIVE_FAILURES,
        help="stop the run after this many identical errors in a row",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=DEFAULT_READY_TIMEOUT_S,
        help="seconds to wait for the model to answer after a settings change",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
