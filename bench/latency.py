"""One request's wait, read from either kind of row.

Two runners write rows that answer the same question: how long until the first token, at what
prompt size, with which helper setting, and what the helper was doing when the request began.
`bench/run.py` writes a speed row (milliseconds under `metrics`); the chat path writes a chat row
(seconds under `server_timing`). This module reads either into one `Request`, so a study about
waits does not have to know which runner wrote the row.

Nothing is typed in: the prompt size, the setting and the failed checks all come from the row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from bench.labels import SETTING_AUTOMATIC, SETTING_MAC_ALONE, layer_setting

# A chat row records the prompt size it asked for; a speed row records the cell it ran. A short
# chat request asks for no particular size, so the prompt it actually read stands in.
SIZE_FIELDS = ("prompt_size", "target_tokens")

# The helper cuts the wait by about three times on the machine pairs measured here, so a request
# that came back in under half the Mac-alone wait cannot have read its prompt on the Mac alone.
HELPER_SPEED_FRACTION = 0.5


@dataclass(frozen=True)
class Request:
    """One request: its wait, its setting, and what its row says about it."""

    machine: str
    path: str  # the arm's path label, from the study entry: "chat" or "speed test"
    arm: str  # the arm label, from the study entry: "no wait" or "wait"
    size: int
    setting: str  # SETTING_MAC_ALONE, SETTING_AUTOMATIC or a pinned layer count
    ttft_s: float
    helper_on: bool
    helper_state: Optional[str]
    helper_wait_s: float
    helper_layers: Optional[int]
    cached_tokens: Optional[int]
    correct: Optional[bool]
    failed: Tuple[str, ...]
    # A speed row carries a validity block; a chat row carries none, and an empty `failed` there
    # means "nothing was checked", not "everything passed".
    checks_recorded: bool

    @property
    def valid(self) -> bool:
        return not self.failed


# The helper states its own program reports, said the way a reader can use them.
STATE_LABELS: Dict[str, str] = {
    "connecting": "not ready yet, still connecting",
    "starting": "not ready yet, still starting",
    "ready": "ready",
    "none": "no state read",
}


def state_label(name: str) -> str:
    """'starting' -> 'not ready yet, still starting'; a state with no plain name keeps its name."""
    return STATE_LABELS.get(name, name)


@dataclass
class Waits:
    """The requests of one cell, read as one line of a table."""

    members: List[Request] = field(default_factory=list)

    def add(self, request: Request) -> None:
        self.members.append(request)

    @property
    def requests(self) -> int:
        return len(self.members)

    @property
    def mean_ttft_s(self) -> float:
        return mean(member.ttft_s for member in self.members)

    @property
    def low_ttft_s(self) -> float:
        return min(member.ttft_s for member in self.members)

    @property
    def high_ttft_s(self) -> float:
        return max(member.ttft_s for member in self.members)

    @property
    def mean_wait_s(self) -> float:
        return mean(member.helper_wait_s for member in self.members)

    @property
    def state_text(self) -> str:
        """Each helper state the requests began in, with its share: 'ready (6 of 6)'."""
        counts: Dict[str, int] = {}
        for member in self.members:
            name = member.helper_state or "none"
            counts[name] = counts.get(name, 0) + 1
        if not counts:
            return state_label("none")
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return " · ".join(f"{state_label(name)} ({count} of {self.requests})" for name, count in ordered)

    @property
    def layers_text(self) -> str:
        """The layer count the helper really took: once when it never changed, else every run."""
        taken = [member.helper_layers for member in self.members]
        if not taken or all(count is None for count in taken):
            return "none"
        if len(set(taken)) == 1:
            return str(taken[0])
        return ", ".join("none" if count is None else str(count) for count in taken)

    @property
    def failed_text(self) -> str:
        """'2 · helper_ready_at_start', '0' when every checked row passed, or a note that no row
        recorded a check at all. A zero for unchecked rows would read as a clean bill of health."""
        marked = [member for member in self.members if member.checks_recorded]
        if not marked:
            return "no validity marks"
        counts: Dict[str, int] = {}
        for member in marked:
            for name in member.failed:
                counts[name] = counts.get(name, 0) + 1
        text = ", ".join(f"{count} · {name}" for name, count in counts.items()) or "0"
        unmarked = len(self.members) - len(marked)
        if unmarked:
            text += f" · {unmarked} row{'s' if unmarked != 1 else ''} unmarked"
        return text

    def at_helper_speed(self, alone: Dict[int, float]) -> int:
        return sum(1 for member in self.members if at_helper_speed(member, alone))


def _int_or_none(value: Any) -> Optional[int]:
    return None if value is None else int(value)


def prompt_size(row: Dict[str, Any]) -> int:
    """The prompt size the row was run at, whichever field names it."""
    for name in SIZE_FIELDS:
        value = row.get(name)
        if value is not None:
            return int(value)
    read = (row.get("usage") or {}).get("prompt_tokens")
    if read is not None:
        return int(read)
    raise ValueError(f"row has no prompt size: no {' or '.join(SIZE_FIELDS)}, no usage.prompt_tokens")


def setting_of(row: Dict[str, Any]) -> str:
    """The setting a row asked for: the Mac alone, the automatic choice, or a pinned layer count."""
    if not row.get("helper_on"):
        return SETTING_MAC_ALONE
    layers = (row.get("desired_settings") or {}).get("prefill_helper_layers")
    return SETTING_AUTOMATIC if layers is None else layer_setting(int(layers))


def ttft_s(row: Dict[str, Any]) -> float:
    """Time to first token in seconds: a speed row gives milliseconds, a chat row seconds."""
    metrics = row.get("metrics") or {}
    if metrics.get("ttft_ms") is not None:
        return float(metrics["ttft_ms"]) / 1000.0
    timing = row.get("server_timing") or {}
    if timing.get("time_to_first_token") is not None:
        return float(timing["time_to_first_token"])
    raise ValueError("row has no time to first token")


def cached_tokens(row: Dict[str, Any]) -> Optional[int]:
    """Cached prompt tokens: a chat row reports them under `usage`, a speed row in its server log."""
    usage = (row.get("usage") or {}).get("cached_tokens")
    if usage is not None:
        return int(usage)
    logged = (row.get("log") or {}).get("cached_tokens")
    return None if logged is None else int(logged)


def failed_checks(row: Dict[str, Any]) -> Tuple[str, ...]:
    """The checks a row failed, by name.

    A speed row carries `validity`, one boolean per rule in `docs/method.md`. A chat row records no
    validity block, so the same three things are read from its own fields: it completed, it read
    its prompt cold, and its answer was right.
    """
    validity = row.get("validity")
    if isinstance(validity, dict):
        # `valid` is the one flag that sums the rest; naming it too would count a row twice.
        return tuple(sorted(name for name, passed in validity.items() if passed is False and name != "valid"))
    failed = []
    if str(row.get("status", "")).lower() != "completed":
        failed.append("status_completed")
    cached = cached_tokens(row)
    if cached is not None and cached != 0:
        failed.append("cached_tokens_zero")
    if row.get("correct") is False:
        failed.append("answer_correct")
    return tuple(failed)


def from_row(row: Dict[str, Any], *, path: str, arm: str) -> Request:
    """One row as a request. `path` and `arm` say where the row was run, as the study names them."""
    correct = row.get("correct")
    return Request(
        machine=str(row.get("machine", "")),
        path=path,
        arm=arm,
        size=prompt_size(row),
        setting=setting_of(row),
        ttft_s=ttft_s(row),
        helper_on=bool(row.get("helper_on")),
        helper_state=row.get("helper_state"),
        helper_wait_s=float(row.get("helper_wait_s") or 0.0),
        helper_layers=_int_or_none(row.get("helper_layers")),
        cached_tokens=cached_tokens(row),
        correct=correct if isinstance(correct, bool) else None,
        failed=failed_checks(row),
        checks_recorded=isinstance(row.get("validity"), dict),
    )


def group_requests(
    requests: Sequence[Request], key: Callable[[Request], Any]
) -> Dict[Any, Waits]:
    """Requests gathered into cells. Cells keep the order the requests arrived in."""
    groups: Dict[Any, Waits] = {}
    for request in requests:
        groups.setdefault(key(request), Waits()).add(request)
    return groups


def mac_alone_wait_s(requests: Sequence[Request]) -> Dict[int, float]:
    """The longest mean wait at each prompt size: how long the Mac alone takes.

    A request that begins before the helper session is up is served by the Mac alone, with no
    error and no warning, so the slowest arm of helper-on requests at one prompt size is that
    Mac-alone wait. It is read from the rows, so no figure is typed in.
    """
    groups = group_requests(requests, lambda request: (request.size, request.path, request.arm))
    alone: Dict[int, float] = {}
    for (size, _, _), waits in groups.items():
        alone[size] = max(alone.get(size, 0.0), waits.mean_ttft_s)
    return alone


def at_helper_speed(request: Request, alone: Dict[int, float]) -> bool:
    """True when the request did not read its whole prompt on the Mac alone.

    A size with no reference in the rows is not judged: it passes.
    """
    reference = alone.get(request.size)
    return True if reference is None else request.ttft_s < reference * HELPER_SPEED_FRACTION
