"""Prefill-helper session state: the field names, the read, and the wait rule.

oMLX unloads the model when its settings change and starts a new helper session on the second
machine. A helper session attaches to a loaded model, and the session from before the change can
still read `ready` for well under a second before it ends. So one `ready` answer proves nothing:
it must hold for `--helper-stable-s` seconds with the same session start (`since`). A request that
arrives before the new session is up is read on the Mac alone, at Mac-alone speed, with no error
in the log.

Every server field name this repository reads is in this module. `name` and `node_id` are in the
answer and are read by nobody: the node id never goes into a row.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

HELPER_STATE_ENDPOINT = "/admin/api/prefill-helper/models/{model}"
HELPER_STATE_FIELD = "state"
HELPER_SINCE_FIELD = "since"
HELPER_LAYERS_FIELD = "layers"
HELPER_HELD_FIELD = "held"
HELPER_LAST_PROMPT_FIELD = "last_prompt"
HELPER_LAST_PROMPT_AT_FIELD = "at"
HELPER_LAST_PROMPT_TOKENS_FIELD = "tokens"
HELPER_LAST_PROMPT_SECONDS_FIELD = "seconds"

HELPER_READY_STATE = "ready"
HELPER_UNKNOWN_STATE = "unknown"

DEFAULT_READY_TIMEOUT_S = 120.0
DEFAULT_STABLE_S = 5.0
POLL_INTERVAL_S = 2.0
MIN_POLL_INTERVAL_S = 0.01

_NO_SPAN = object()


def request_clock() -> float:
    """Wall-clock epoch seconds: the server reports `last_prompt.at` on the same clock."""
    return time.time()


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _whole(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None else None


@dataclass(frozen=True)
class HelperStatus:
    """One answer about the helper session, and the wait that came before it."""

    state: Optional[str]
    since: Optional[float] = None
    layers: Optional[int] = None
    held: Optional[int] = None
    last_prompt_at: Optional[float] = None
    last_prompt_tokens: Optional[int] = None
    last_prompt_seconds: Optional[float] = None
    waited_s: float = 0.0
    # Whether the wait saw `ready` hold long enough to be trusted; None when no wait ran.
    stable: Optional[bool] = None

    @property
    def is_ready(self) -> bool:
        return self.state == HELPER_READY_STATE

    @property
    def ready_for_request(self) -> bool:
        """Up, and stable when a wait ran: a `ready` the wait did not trust does not count."""
        return self.is_ready and self.stable is not False

    @classmethod
    def off(cls) -> "HelperStatus":
        """The helper was off, so the server was not asked."""
        return cls(state=None)

    @classmethod
    def unknown(cls) -> "HelperStatus":
        """The server was asked (or about to be) and no state was read."""
        return cls(state=HELPER_UNKNOWN_STATE)

    @classmethod
    def from_response(cls, payload: Any) -> "HelperStatus":
        """Read the fields above. A missing or unreadable one becomes None and the state becomes
        `unknown`: a state the row can carry, never a crash."""
        if not isinstance(payload, Mapping):
            return cls.unknown()
        state = payload.get(HELPER_STATE_FIELD)
        prompt = payload.get(HELPER_LAST_PROMPT_FIELD)
        prompt = prompt if isinstance(prompt, Mapping) else {}
        state_text = state.strip().lower() if isinstance(state, str) and state.strip() else HELPER_UNKNOWN_STATE
        return cls(
            state=state_text,
            since=_number(payload.get(HELPER_SINCE_FIELD)),
            layers=_whole(payload.get(HELPER_LAYERS_FIELD)),
            held=_whole(payload.get(HELPER_HELD_FIELD)),
            last_prompt_at=_number(prompt.get(HELPER_LAST_PROMPT_AT_FIELD)),
            last_prompt_tokens=_whole(prompt.get(HELPER_LAST_PROMPT_TOKENS_FIELD)),
            last_prompt_seconds=_number(prompt.get(HELPER_LAST_PROMPT_SECONDS_FIELD)),
        )


@dataclass(frozen=True)
class HelperWaitPolicy:
    """Whether to wait for a stable helper session, and how long to give it."""

    timeout_s: float = DEFAULT_READY_TIMEOUT_S
    stable_s: float = DEFAULT_STABLE_S
    wait: bool = True

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "HelperWaitPolicy":
        return cls(
            timeout_s=float(args.helper_ready_timeout),
            stable_s=float(args.helper_stable_s),
            wait=not args.no_helper_wait,
        )


def add_wait_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the helper-wait options to a runner's parser."""
    parser.add_argument(
        "--helper-ready-timeout",
        type=float,
        default=DEFAULT_READY_TIMEOUT_S,
        metavar="SECONDS",
        help="seconds to wait for the helper session after a settings change (default 120)",
    )
    parser.add_argument(
        "--helper-stable-s",
        type=float,
        default=DEFAULT_STABLE_S,
        metavar="SECONDS",
        help="how long `ready` must hold with one session start before it is trusted (default 5)",
    )
    parser.add_argument(
        "--no-helper-wait",
        action="store_true",
        help="do not wait for the helper session; read its state once (old behaviour, for replay)",
    )


def read_helper_state(read: Callable[[str], Any], model: str) -> HelperStatus:
    """One state read. An HTTP error or an unreadable answer is `unknown`, not a failure."""
    try:
        payload = read(model)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read the helper state for %s: %s", model, exc)
        return HelperStatus.unknown()
    return HelperStatus.from_response(payload)


def wait_for_helper_ready(
    read: Callable[[str], Any],
    model: str,
    *,
    timeout_s: float = DEFAULT_READY_TIMEOUT_S,
    stable_s: float = DEFAULT_STABLE_S,
    interval_s: float = POLL_INTERVAL_S,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> HelperStatus:
    """Poll until `ready` has held for `stable_s` with one session start, or the timeout passes.

    A change of `since`, or any state that is not `ready`, starts the span again, so the session
    that reads `ready` for a moment on its way out cannot pass for the new one. The last state
    seen comes back with the seconds spent, so a run that gives up still records what the helper
    was doing. Never raises.
    """
    interval_s = max(float(interval_s), MIN_POLL_INTERVAL_S)
    stable_s = max(float(stable_s), 0.0)
    started = clock()
    deadline = started + max(float(timeout_s), 0.0)

    status = read_helper_state(read, model)
    span_since: Any = status.since if status.is_ready else _NO_SPAN
    span_start = clock()

    while True:
        if status.is_ready and span_since is not _NO_SPAN and clock() - span_start >= stable_s:
            return replace(status, waited_s=round(clock() - started, 3), stable=True)
        now = clock()
        if now >= deadline:
            logger.warning(
                "Helper for %s not stable-ready after %.1fs (state %r); sending the request anyway",
                model,
                now - started,
                status.state,
            )
            return replace(status, waited_s=round(now - started, 3), stable=False)
        sleep(min(interval_s, deadline - now))
        status = read_helper_state(read, model)
        if status.is_ready and span_since is not _NO_SPAN and status.since == span_since:
            continue
        if status.is_ready:
            span_since = status.since
        else:
            span_since = _NO_SPAN
        span_start = clock()


def prepare_helper(
    client: Any,
    model: str,
    policy: HelperWaitPolicy,
    *,
    helper_on: bool,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> HelperStatus:
    """The helper state for the request about to be sent.

    `client` is the admin client (anything with `get_prefill_helper_state`). With the helper
    off the server is not asked. Without the wait, the state is still read once and recorded,
    so a replay row can show that the session was not up.
    """
    if not helper_on:
        return HelperStatus.off()
    read = client.get_prefill_helper_state
    if not policy.wait:
        return read_helper_state(read, model)
    return wait_for_helper_ready(
        read,
        model,
        timeout_s=policy.timeout_s,
        stable_s=policy.stable_s,
        clock=clock,
        sleep=sleep,
    )


def helper_fields(start: HelperStatus, proof: Optional[HelperStatus] = None) -> Dict[str, Any]:
    """The helper fields of one row: the state at its request, plus the proof read after it."""
    fields: Dict[str, Any] = {
        "helper_state": start.state,
        "helper_wait_s": start.waited_s,
    }
    if proof is not None:
        fields.update(
            {
                "helper_layers": proof.layers,
                "helper_held": proof.held,
                "helper_session_since": proof.since,
                "helper_last_prompt_at": proof.last_prompt_at,
                "helper_last_prompt_tokens": proof.last_prompt_tokens,
                "helper_last_prompt_seconds": proof.last_prompt_seconds,
            }
        )
    return fields


def helper_served(proof: HelperStatus, request_started_at: Optional[float]) -> Optional[bool]:
    """Did the helper serve this request?

    True with the helper off. True when `last_prompt.at` is at or after the request start (one
    clock: the harness runs on the Mac). False when the helper's last prompt is older than the
    request, so the prompt was read on the Mac. None when the field could not be read; such a
    row is not failed by this rule.
    """
    if proof.state is None:
        return True
    if proof.last_prompt_at is None or request_started_at is None:
        return None
    return float(proof.last_prompt_at) >= float(request_started_at)
