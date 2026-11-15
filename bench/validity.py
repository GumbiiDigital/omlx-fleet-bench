"""Benchmark run validity checks."""

from __future__ import annotations

from typing import Any, Dict, List


def assess_validity(
    *,
    status: str,
    end_event_type: str,
    feature_keys: List[str],
    helper_on: bool,
    ane_on: bool,
    log_parsed: Dict[str, Any],
) -> Dict[str, Any]:
    """Return validity booleans and aggregate valid flag (never drop rows)."""
    cached = log_parsed.get("cached_tokens")
    # Observed ANE MLP operations prove the ANE ran; full_ane_tiles can be an estimate.
    ane_ops = log_parsed.get("ane_mlp_operations")

    status_ok = str(status).lower() == "completed"
    upload_ok = end_event_type == "upload_skipped"
    cached_ok = cached == 0

    expect_prefill_accel = helper_on
    has_prefill_accel = "prefill_accelerator" in feature_keys
    helper_ok = has_prefill_accel == expect_prefill_accel

    if ane_on:
        ane_ok = ane_ops is not None and int(ane_ops) > 0
    else:
        ane_ok = ane_ops is not None and int(ane_ops) == 0

    valid = status_ok and upload_ok and cached_ok and helper_ok and ane_ok

    return {
        "valid": valid,
        "status_completed": status_ok,
        "upload_skipped": upload_ok,
        "cached_tokens_zero": cached_ok,
        "helper_flag_match": helper_ok,
        "ane_tiles_match": ane_ok,
    }