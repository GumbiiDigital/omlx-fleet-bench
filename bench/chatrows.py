"""One chat request's row, and the rule that stops a run, written once for both chat runners.

`bench/quality.py` asks one question per request and scores the answer; `bench/concurrency.py`
sends many requests at one moment and measures the wait. Both keep rows of the same shape: the
run's fixed facts, the helper state at the request, then the reply or its error. That shape, the
write, and the stop rule live here so one reader can read either file and a row cannot drift
between the two runners.

Nothing here measures anything: the caller keeps the fields its own question needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bench.helper import HelperStatus, helper_fields

DEFAULT_MAX_CONSECUTIVE_FAILURES = 5


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
class ChatRunContext:
    """Fixed facts that every row of one run shares."""

    machine: str
    matrix_path: str
    model: str
    fields: List[str]
    out_path: Path
    total_units: int


def append_row(path: Path, row: Dict[str, Any]) -> None:
    """Add one row to the run's file, making its folder when it is missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def row_base(
    context: ChatRunContext,
    *,
    variant_name: str,
    helper_on: bool,
    ane_on: bool,
    desired: Dict[str, Any],
    original: Dict[str, Any],
    helper: HelperStatus,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """The part of a chat row that every chat request has, before its reply is known."""
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "machine": context.machine,
        "matrix": context.matrix_path,
        "model": context.model,
        "variant": variant_name,
        "helper_on": helper_on,
        **helper_fields(helper),
        "ane_on": ane_on,
        "desired_settings": {k: desired.get(k) for k in context.fields},
        "settings_before": original,
    }


def request_fields(reply: Dict[str, Any]) -> Dict[str, Any]:
    """What one answered request records, whatever else its row measures."""
    return {
        "status": "completed",
        "finish_reason": reply["finish_reason"],
        "content": reply["content"],
        "reasoning_chars": len(reply["reasoning"]),
        "usage": reply["usage"],
        "server_timing": reply["server_timing"],
        "latency_s": reply["latency_s"],
    }


def error_fields(error: Any) -> Dict[str, Any]:
    """What a failed request records. The row is kept, so the failure is part of the result."""
    return {"status": "error", "error": str(error)}
