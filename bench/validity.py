"""Benchmark run validity checks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def assess_validity(
    *,
    status: str,
    end_event_type: str,
    feature_keys: List[str],
    helper_on: bool,
    ane_on: bool,
    log_parsed: Dict[str, Any],
    helper_ready: Optional[bool] = None,
) -> Dict[str, Any]:
    """Return validity booleans and aggregate valid flag (never drop rows).

    `helper_ready` is the helper state read at the start of the request: with the helper on, a
    session that was not up means the prompt was read on the Mac alone. None means the row did
    not record a state (an older row, or a run before this check existed): the rule passes, so
    those rows keep the validity they were given.
    """
    cached = log_parsed.get("cached_tokens")
    # Observed ANE MLP operations prove the ANE ran; full_ane_tiles can be an estimate.
    ane_ops = log_parsed.get("ane_mlp_operations")

    status_ok = str(status).lower() == "completed"
    upload_ok = end_event_type == "upload_skipped"
    cached_ok = cached == 0

    expect_prefill_accel = helper_on
    has_prefill_accel = "prefill_accelerator" in feature_keys
    helper_ok = has_prefill_accel == expect_prefill_accel

    # The helper was off, or the session was up when the request started. A row that carries
    # no state (an older row) passes, so old files keep their meaning.
    helper_ready_ok = True if (not helper_on or helper_ready is None) else bool(helper_ready)

    if ane_on:
        ane_ok = ane_ops is not None and int(ane_ops) > 0
    else:
        ane_ok = ane_ops is not None and int(ane_ops) == 0

    valid = status_ok and upload_ok and cached_ok and helper_ok and ane_ok and helper_ready_ok

    return {
        "valid": valid,
        "status_completed": status_ok,
        "upload_skipped": upload_ok,
        "cached_tokens_zero": cached_ok,
        "helper_flag_match": helper_ok,
        "helper_ready_at_start": helper_ready_ok,
        "ane_tiles_match": ane_ok,
    }