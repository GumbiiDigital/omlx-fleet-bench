"""Prefill-helper session state: one reader, one wait policy.

oMLX unloads the model when its settings change, and the helper manager ends the old helper
session and starts a new one on the second machine. A request that arrives before that session
is attached is read on the Mac alone, at Mac-alone speed, with no error in the log. A run that
measures the helper must therefore wait for the session, and every row must say what state it
found at its own request.

The read (one endpoint, one field name) and the wait (one poll loop) live in this module so both
runners share them, and a change of field name is a change in one place.
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

logger = logging.getLogger(__name__)

# The only names taken from the server's answer. `state` reads `ready` once the helper session
# holds the layers and can take a prompt; anything else is a session that cannot take work yet.
HELPER_STATE_ENDPOINT = "/admin/api/prefill-helper/models/{model}"
HELPER_STATE_FIELD = "state"
HELPER_READY_STATE = "ready"
HELPER_UNKNOWN_STATE = "unknown"

DEFAULT_READY_TIMEOUT_S = 120.0
POLL_INTERVAL_S = 2.0
MIN_POLL_INTERVAL_S = 0.01


@dataclass(frozen=True)
class HelperStatus:
    """What the server said about the helper session, and the wait that came before it."""

    state: Optional[str]
    waited_s: float = 0.0

    @property
    def is_ready(self) -> bool:
        return self.state == HELPER_READY_STATE

    @classmethod
    def off(cls) -> "HelperStatus":
        """The helper was off, so the server was not asked."""
        return cls(state=None)

    @classmethod
    def from_response(cls, payload: Any) -> "HelperStatus":
        """Read the state field. A missing field, an empty one or a different shape is
        `unknown`: a state the row can carry, never a crash."""
        if isinstance(payload, Mapping):
            value = payload.get(HELPER_STATE_FIELD)
            if isinstance(value, str) and value.strip():
                return cls(state=value.strip().lower())
        return cls(state=HELPER_UNKNOWN_STATE)


@dataclass(frozen=True)
class HelperWaitPolicy:
    """Whether to wait for the helper session, and for how long."""

    timeout_s: float = DEFAULT_READY_TIMEOUT_S
    wait: bool = True

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "HelperWaitPolicy":
        return cls(
            timeout_s=float(args.helper_ready_timeout),
            wait=not args.no_helper_wait,
        )


def add_wait_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the two helper-wait options to a runner's parser."""
    parser.add_argument(
        "--helper-ready-timeout",
        type=float,
        default=DEFAULT_READY_TIMEOUT_S,
        metavar="SECONDS",
        help="seconds to wait for the helper session after a settings change (default 120)",
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
        return HelperStatus(state=HELPER_UNKNOWN_STATE)
    return HelperStatus.from_response(payload)


def wait_for_helper_ready(
    read: Callable[[str], Any],
    model: str,
    *,
    timeout_s: float = DEFAULT_READY_TIMEOUT_S,
    interval_s: float = POLL_INTERVAL_S,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> HelperStatus:
    """Poll the helper state until it is `ready` or the timeout passes. Never raises.

    The last state seen is returned with the seconds spent, so a run that gives up still
    records what the helper was doing.
    """
    interval_s = max(float(interval_s), MIN_POLL_INTERVAL_S)
    started = clock()
    deadline = started + max(float(timeout_s), 0.0)
    status = read_helper_state(read, model)
    while not status.is_ready:
        now = clock()
        if now >= deadline:
            logger.warning(
                "Helper for %s not ready after %.1fs (state %r); sending the request anyway",
                model,
                now - started,
                status.state,
            )
            break
        sleep(min(interval_s, deadline - now))
        status = read_helper_state(read, model)
    return HelperStatus(state=status.state, waited_s=round(clock() - started, 3))


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
    return wait_for_helper_ready(read, model, timeout_s=policy.timeout_s, clock=clock, sleep=sleep)
