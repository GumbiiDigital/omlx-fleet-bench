#!/usr/bin/env python3
"""Many users: N chat requests that begin at one moment, and one JSONL row per request.

Usage:
    python3 bench/concurrency.py --matrix matrices/m3-ultra-b-many-users.json \
        --base-url http://127.0.0.1:8004 --settings ~/.omlx/settings.json \
        --helper-node NODE_ID --machine my-mac --out results/my-mac/many-users-DATE.jsonl

One wave is one prompt size, one setting, and N requests (`--users`) released together. Before the
first wave of a setting the runner sends the settings, probes the model and waits for the helper
through `bench/runflow.py` — the one home of that order — because a request that begins before the
helper session is ready is read by the Mac alone, with no error. Each request of a wave carries its
own prompt (a unique first line), so no request is answered from another's prompt cache, and each
is sent exactly once: a retry would start after its wave and its time would cover one attempt only.
The settings are restored when the run ends, also after a failure.

Rows have the shape of a chat row (`bench/chatrows.py`, `bench/quality.py`) plus the wave fields.
Nothing is uploaded anywhere: the chat path has no leaderboard upload.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bench.chat import DEFAULT_READY_TIMEOUT_S, ChatClient, ChatError  # noqa: E402
from bench.chatrows import (  # noqa: E402
    DEFAULT_MAX_CONSECUTIVE_FAILURES,
    ChatRunContext,
    ConsecutiveFailureGuard,
    append_row,
    error_fields,
    request_fields,
    row_base,
)
from bench.client import OMLXClient, load_api_key  # noqa: E402
from bench.helper import (  # noqa: E402
    HelperStatus,
    HelperWaitPolicy,
    add_wait_arguments,
    helper_fields,
    helper_served,
    request_clock,
)
from bench.matrix import (  # noqa: E402
    SettingsVariant,
    settings_fields_touched,
    settings_variant,
)
from bench.qa import approximate_tokens, build_passkey_prompt, prompt_messages, score_passkey  # noqa: E402
from bench.runflow import begin_request, end_request, state_at_request  # noqa: E402
from bench.validity import assess_many_users_validity  # noqa: E402

logger = logging.getLogger("bench.concurrency")

TASK_NAME = "many_users"
DEFAULT_TIMEOUT_S = 900.0
NEEDLES = ("4829157", "7304826", "5940271")


@dataclass(frozen=True)
class WavePlan:
    """One wave scheduled by the matrix: a setting, a prompt size, a user count, a repeat."""

    variant: SettingsVariant
    prompt_size: int
    users: int
    wave: int

    @property
    def wave_id(self) -> str:
        """The same for every request of this wave and unique within the run."""
        return f"{self.variant.name}-{self.prompt_size}-u{self.users}-w{self.wave}"


@dataclass(frozen=True)
class WaveRequest:
    """One request of a wave: its own prompt, and the number buried in it."""

    index: int
    needle: str
    prompt: str

    @property
    def messages(self) -> List[Dict[str, str]]:
        return prompt_messages(self.prompt)


@dataclass
class WaveOutcome:
    """What one request of a wave returned, or why it returned nothing."""

    index: int
    started_at: float
    reply: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class WaveResult:
    """One wave: the moment it opened, how long it took, and one outcome per request."""

    started_at: float
    wall_s: float
    outcomes: List[WaveOutcome]

    @property
    def answered(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.error is None)


def load_many_users_matrix(path: str) -> Dict[str, Any]:
    """Load a many-users matrix and check it names everything a run needs."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("model", "variants", "prompt_sizes", "users", "waves", "max_tokens"):
        if key not in data:
            raise ValueError(f"many-users matrix needs '{key}'")
    if int(data["waves"]) < 1:
        raise ValueError("many-users matrix needs at least one wave")
    if not [int(size) for size in data["prompt_sizes"]]:
        raise ValueError("many-users matrix needs at least one prompt size")
    return data


def parse_users(raw: Optional[str]) -> Optional[List[int]]:
    """Read `--users 1,2,4,8`; None keeps the matrix's list."""
    if not raw:
        return None
    users = [int(part) for part in raw.split(",") if part.strip()]
    if not users or any(count < 1 for count in users):
        raise ValueError("--users needs counts of 1 or more, for example 1,2,4,8")
    return users


def matrix_variants(matrix: Dict[str, Any]) -> List[SettingsVariant]:
    return [settings_variant(raw) for raw in matrix["variants"]]


def waves_for(
    matrix: Dict[str, Any],
    *,
    users: Optional[Sequence[int]] = None,
    waves: Optional[int] = None,
) -> List[WavePlan]:
    """Every wave in run order: prompt size, then setting, then user count, then repeat.

    The matrix's own variant order is kept, so the Mac-alone setting runs before the helper
    setting at each prompt size. One settings change covers a whole block of waves.
    """
    counts = [int(count) for count in (users if users is not None else matrix["users"])]
    repeats = int(matrix["waves"] if waves is None else waves)
    if repeats < 1:
        raise ValueError("a run needs at least one wave")
    plans: List[WavePlan] = []
    for size in [int(size) for size in matrix["prompt_sizes"]]:
        for variant in matrix_variants(matrix):
            for count in counts:
                for wave in range(repeats):
                    plans.append(WavePlan(variant=variant, prompt_size=size, users=count, wave=wave))
    return plans


def wave_requests(plan: WavePlan) -> List[WaveRequest]:
    """One fresh prompt per user of the wave, so no two requests read the same text.

    The first line carries the wave, the user and the repeat, so the server cannot answer a
    request from the prompt cache of another one; that is what keeps `cached_tokens` at 0.
    """
    requests: List[WaveRequest] = []
    for index in range(plan.users):
        needle = NEEDLES[(plan.wave * plan.users + index) % len(NEEDLES)]
        prompt = build_passkey_prompt(
            plan.prompt_size, needle, cache_tag=f"{plan.wave_id}-{index}"
        )
        requests.append(WaveRequest(index=index, needle=needle, prompt=prompt))
    return requests


def send_wave(
    sends: Sequence[Callable[[], Dict[str, Any]]],
    *,
    clock: Callable[[], float] = request_clock,
) -> WaveResult:
    """Send every request at one moment and return once all of them are done.

    A barrier holds one thread per request until the last one is ready to send, so no request can
    start before the whole wave does; the instant the barrier opens is the wave start, and each
    request records its own start, which gives its offset from the wave. A request that fails is
    kept as its error text: one failure is a row, not the end of the wave.
    """
    if not sends:
        raise ValueError("a wave needs at least one request")
    count = len(sends)
    started: List[float] = [0.0] * count
    opened: Dict[str, float] = {}
    outcomes: List[Optional[WaveOutcome]] = [None] * count

    def open_gate() -> None:
        opened.setdefault("at", clock())

    gate = threading.Barrier(count, action=open_gate)

    def send_one(index: int, send: Callable[[], Dict[str, Any]]) -> None:
        gate.wait()
        started[index] = clock()
        try:
            reply = send()
        except Exception as exc:  # noqa: BLE001 — one request's error becomes its row
            outcomes[index] = WaveOutcome(index=index, started_at=started[index], error=str(exc))
            return
        outcomes[index] = WaveOutcome(index=index, started_at=started[index], reply=reply)

    threads = [
        threading.Thread(target=send_one, args=(index, send), name=f"many-users-{index}", daemon=True)
        for index, send in enumerate(sends)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    wave_start = opened.get("at", clock())
    wall_s = round(max(clock() - wave_start, 0.0), 3)
    filled = [
        outcome
        if outcome is not None
        else WaveOutcome(
            index=index,
            started_at=0.0,
            error="request did not run: the wave gate closed before it was sent",
        )
        for index, outcome in enumerate(outcomes)
    ]
    return WaveResult(started_at=wave_start, wall_s=wall_s, outcomes=filled)


def wave_rows(
    context: ChatRunContext,
    plan: WavePlan,
    requests: Sequence[WaveRequest],
    result: WaveResult,
    *,
    desired: Dict[str, Any],
    original: Dict[str, Any],
    helper: HelperStatus,
    proof: HelperStatus,
    max_tokens: int,
) -> List[Dict[str, Any]]:
    """One row per request of the wave, each with the wave's own fields and a validity block."""
    rows: List[Dict[str, Any]] = []
    for request, outcome in zip(requests, result.outcomes):
        row = row_base(
            context,
            variant_name=plan.variant.name,
            helper_on=plan.variant.helper_on,
            ane_on=plan.variant.ane_on,
            desired=desired,
            original=original,
            helper=helper,
        )
        row.update(
            {
                "task": TASK_NAME,
                "sample_id": f"{plan.wave_id}-{request.index}",
                "max_tokens": max_tokens,
                "target_tokens": plan.prompt_size,
                "prompt_chars": len(request.prompt),
                "approximate_prompt_tokens": approximate_tokens(request.prompt),
                "expected": request.needle,
                "users": plan.users,
                "wave": plan.wave,
                "wave_id": plan.wave_id,
                "user_index": request.index,
                "wave_wall_s": result.wall_s,
                "request_start_offset_s": (
                    round(outcome.started_at - result.started_at, 3) if outcome.started_at else None
                ),
            }
        )
        reply = outcome.reply
        if reply is None:
            row.update({**error_fields(outcome.error or "request returned no reply"), "correct": False})
        else:
            row.update(request_fields(reply))
            row.update(score_passkey(reply["content"], request.needle))
            if not reply["content"].strip():
                row["note"] = "no_answer_text"
        row.update(helper_fields(helper, proof))
        row["validity"] = assess_many_users_validity(
            status=str(row.get("status", "")),
            cached_tokens=(row.get("usage") or {}).get("cached_tokens"),
            helper_on=plan.variant.helper_on,
            helper_state=helper.state,
            wave_users=plan.users,
            wave_answered=result.answered,
            helper_served=helper_served(proof, result.started_at),
        )
        rows.append(row)
    return rows


def blocks_of(plans: Sequence[WavePlan]) -> List[Tuple[int, SettingsVariant, List[WavePlan]]]:
    """Consecutive waves that share one prompt size and one setting: one settings change each."""
    blocks: List[Tuple[Tuple[int, str], List[WavePlan]]] = []
    for plan in plans:
        key = (plan.prompt_size, plan.variant.name)
        if not blocks or blocks[-1][0] != key:
            blocks.append((key, []))
        blocks[-1][1].append(plan)
    return [(key[0], items[0].variant, items) for key, items in blocks]


def prepare_output(path: Path) -> None:
    """Make the output folder and prove the file can be written, before the first request."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8"):
        pass


def run(args: argparse.Namespace) -> int:
    matrix = load_many_users_matrix(args.matrix)
    base_settings = dict(matrix.get("base_settings") or {})
    plans = waves_for(matrix, users=parse_users(args.users), waves=args.waves)
    max_tokens = int(matrix["max_tokens"])
    temperature = float(matrix.get("temperature", 0.0))
    fields = settings_fields_touched([], base_settings)
    out_path = Path(args.out)

    if args.dry_run:
        for plan in plans:
            print(
                f"{plan.wave_id}: {plan.users} request(s) at ~{plan.prompt_size} tokens, "
                f"setting {plan.variant.name}"
            )
        print(f"Total waves: {len(plans)}, requests: {sum(plan.users for plan in plans)}")
        return 0

    try:
        prepare_output(out_path)
    except OSError as exc:
        print(f"cannot write {out_path}: {exc}", file=sys.stderr)
        return 2

    api_key = load_api_key(args.settings)
    admin = OMLXClient(args.base_url, api_key)
    admin.login()
    chat = ChatClient(args.base_url, api_key, timeout_s=args.timeout)
    policy = HelperWaitPolicy.from_args(args)
    guard = ConsecutiveFailureGuard(args.max_consecutive_failures)
    context = ChatRunContext(
        machine=args.machine,
        matrix_path=str(Path(args.matrix)),
        model=matrix["model"],
        fields=fields,
        out_path=out_path,
        total_units=sum(plan.users for plan in plans),
    )
    written = 0

    with admin.preserved_settings(matrix["model"], fields) as original:
        for size, variant, block in blocks_of(plans):
            desired = variant.merge_settings(base_settings, args.helper_node or "")
            try:
                # Settings, then a probe that makes the model load, then the helper wait.
                helper = begin_request(
                    admin,
                    chat,
                    matrix["model"],
                    desired,
                    fields,
                    policy,
                    helper_on=variant.helper_on,
                    ready_timeout_s=args.ready_timeout,
                )
            except ChatError as exc:
                logger.error("Model not ready for %s at %d tokens: %s", variant.name, size, exc)
                logger.error("Run stopped after %d rows; settings are restored", written)
                return 1
            first = True
            for plan in block:
                at_wave = state_at_request(
                    admin,
                    matrix["model"],
                    helper_on=variant.helper_on,
                    after_settings=helper if first else None,
                )
                first = False
                requests = wave_requests(plan)
                # One attempt per request: a retry inside a wave would start after the wave and its
                # time would cover the last attempt only, and a failure would pass for an answer.
                sends = [
                    partial(
                        chat.chat,
                        matrix["model"],
                        request.messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        retries=0,
                    )
                    for request in requests
                ]
                result = send_wave(sends)
                proof = end_request(admin, matrix["model"], helper_on=variant.helper_on)
                rows = wave_rows(
                    context,
                    plan,
                    requests,
                    result,
                    desired=desired,
                    original=original,
                    helper=at_wave,
                    proof=proof,
                    max_tokens=max_tokens,
                )
                for row in rows:
                    append_row(out_path, row)
                written += len(rows)
                logger.info(
                    "Wrote %d rows for %s: %d of %d answered, wave %.2fs",
                    len(rows),
                    plan.wave_id,
                    result.answered,
                    plan.users,
                    result.wall_s,
                )
                stop = False
                for outcome in result.outcomes:
                    if outcome.error is None:
                        guard.record_success()
                    elif guard.record_failure(outcome.error):
                        stop = True
                if stop:
                    logger.error(
                        "Stopped after %d identical failures in a row (wave %s); wrote %d rows",
                        guard.count,
                        plan.wave_id,
                        written,
                    )
                    return 1

    logger.info("Wrote %d rows to %s", written, out_path)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="oMLX many-users runner")
    parser.add_argument("--matrix", required=True, help="Path to a many-users matrix JSON")
    parser.add_argument("--base-url", required=True, help="oMLX admin base URL")
    parser.add_argument("--settings", required=True, help="oMLX settings.json path")
    parser.add_argument("--out", required=True, help="JSONL output path; its folder is made when missing")
    parser.add_argument("--machine", required=True, help="Machine label for results")
    parser.add_argument("--helper-node", default="", help="Spark helper node id")
    parser.add_argument(
        "--users",
        default=None,
        metavar="LIST",
        help="comma separated user counts, an override of the matrix (for example 1,2,4,8)",
    )
    parser.add_argument(
        "--waves",
        type=int,
        default=None,
        metavar="N",
        help="waves per user count, an override of the matrix",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        metavar="SECONDS",
        help="seconds to wait for one request (default 900)",
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
    parser.add_argument("--dry-run", action="store_true", help="print the waves and send nothing")
    parser.add_argument("-v", "--verbose", action="store_true")
    add_wait_arguments(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
