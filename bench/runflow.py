"""The order of calls around a measured request, written once for both runners.

A settings change unloads the model and reloads it, and the helper starts a new session that
attaches to the loaded model. So before a request the harness must, in this order: send the
settings, ask the model for one token so the load happens, and then wait for a stable helper
session. After the request it reads the helper once more, for the proof that the helper served it.

Both harnesses call these functions, so the order has one copy and the speed harness cannot fall
back to reading the helper before the model has loaded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bench.helper import (
    HelperStatus,
    HelperWaitPolicy,
    prepare_helper,
    read_helper_state,
)


def begin_request(
    admin: Any,
    chat: Any,
    model: str,
    desired: Dict[str, Any],
    fields: List[str],
    policy: HelperWaitPolicy,
    *,
    helper_on: bool,
    ready_timeout_s: float,
) -> HelperStatus:
    """Apply the settings, probe the model, then wait for the helper. Return the helper state."""
    admin.apply_settings(model, desired, fields)
    chat.wait_until_ready(model, timeout_s=ready_timeout_s)
    return prepare_helper(admin, model, policy, helper_on=helper_on)


def state_at_request(
    admin: Any,
    model: str,
    *,
    helper_on: bool,
    after_settings: Optional[HelperStatus] = None,
) -> HelperStatus:
    """The helper state for one request, without waiting.

    The first request after a settings change uses the state the wait ended on; each later one
    reads the state again, because a session can end between two requests of one block.
    """
    if not helper_on:
        return HelperStatus.off()
    if after_settings is not None:
        return after_settings
    return read_helper_state(admin.get_prefill_helper_state, model)


def end_request(admin: Any, model: str, *, helper_on: bool) -> HelperStatus:
    """One read after the request: what the helper last served, and how many layers it holds."""
    if not helper_on:
        return HelperStatus.off()
    return read_helper_state(admin.get_prefill_helper_state, model)
