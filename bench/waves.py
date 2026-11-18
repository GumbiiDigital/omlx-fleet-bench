"""Waves of many requests: the requests of one arm, prompt size and user count, read cell by cell.

A many-users row (`bench/concurrency.py`) is a chat row about one request of a wave: N requests
that begin at one moment. `bench/latency.py` reads that row as one request; this module adds the
three fields a wave has and no single request does — how many users it had, which repeat it was,
and how long the whole wave took — and gathers the requests of every wave of a cell together.

Nothing is typed in: the prompt size, the user count and the arm all come from the row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bench import latency
from bench.labels import ARM_ALONE, ARM_HELPER, arm_label, ordered_arms, size_label


@dataclass(frozen=True)
class Member:
    """One request of one wave, with the wave's own figures beside it."""

    request: latency.Request  # the request the row describes: its wait, checks and answer
    users: int
    wave: int
    wall_s: float  # wall time of the whole wave, the same on every row of that wave
    prompt_tokens: int  # prompt tokens this request read

    @property
    def arm(self) -> str:
        return self.request.arm

    @property
    def size(self) -> int:
        return self.request.size


@dataclass
class WaveCell:
    """One arm at one prompt size and one user count: every request of every wave of it."""

    size: int
    arm: str
    users: int
    members: List[Member] = field(default_factory=list)

    def add(self, member: Member) -> None:
        self.members.append(member)

    @property
    def requests(self) -> int:
        return len(self.members)

    @property
    def valid_members(self) -> List[Member]:
        return [member for member in self.members if member.request.valid]

    @property
    def n_valid(self) -> int:
        return len(self.valid_members)

    @property
    def waves(self) -> Dict[int, List[Member]]:
        """The requests of each wave, in wave order."""
        groups: Dict[int, List[Member]] = {}
        for member in self.members:
            groups.setdefault(member.wave, []).append(member)
        return dict(sorted(groups.items()))

    @property
    def valid_waves(self) -> Dict[int, List[Member]]:
        """The waves with no request a flag marks not valid: the ones whose own figures are used.

        A wave is over when its last reply arrives, so one failed request leaves the wave with no
        honest whole-wave time; that wave is kept in the report and left out of the wave means as a
        whole, rather than counted with its slow or short figure.
        """
        return {
            wave: members
            for wave, members in self.waves.items()
            if all(member.request.valid for member in members)
        }

    @property
    def waves_used(self) -> int:
        """How many waves this cell's means rest on: the ones no flag touches."""
        return len(self.valid_waves)

    @property
    def has_valid_wave(self) -> bool:
        """True when at least one wave of the cell has no request a flag marks not valid."""
        return bool(self.valid_waves)

    @property
    def mean_ttft_s(self) -> float:
        valid = self.valid_members
        if not valid:
            raise ValueError(f"{self.arm} at {self.size} with {self.users} users has no valid request")
        return mean(member.request.ttft_s for member in valid)

    @property
    def low_ttft_s(self) -> float:
        return min(member.request.ttft_s for member in self.valid_members)

    @property
    def high_ttft_s(self) -> float:
        return max(member.request.ttft_s for member in self.valid_members)

    def wave_wall_s(self, wave: int) -> float:
        """Wall time of one wave. Every row of a wave carries the same figure."""
        return max(member.wall_s for member in self.waves[wave])

    @property
    def mean_wall_s(self) -> float:
        usable = self.valid_waves
        if not usable:
            raise ValueError(f"{self.arm} at {self.size} with {self.users} users has no valid wave")
        return mean(max(member.wall_s for member in members) for members in usable.values())

    @property
    def mean_prompt_tps(self) -> float:
        """Prompt tokens of all users together, over the wall time of their wave, mean of the waves."""
        usable = self.valid_waves
        if not usable:
            raise ValueError(f"{self.arm} at {self.size} with {self.users} users has no valid wave")
        return mean(
            sum(member.prompt_tokens for member in members) / max(member.wall_s for member in members)
            for members in usable.values()
        )


def arm_of(row: Dict[str, Any]) -> str:
    """The arm a row ran in: the Mac alone when its helper was off, otherwise with the helper."""
    return ARM_HELPER if row.get("helper_on") else ARM_ALONE


def _prompt_tokens(row: Dict[str, Any]) -> int:
    read = (row.get("usage") or {}).get("prompt_tokens")
    if read is None:
        raise ValueError("many-users row has no usage.prompt_tokens, so the wave's speed is unknown")
    return int(read)


def from_row(row: Dict[str, Any]) -> Member:
    """One many-users row as a member of its wave."""
    for name in ("users", "wave", "wave_wall_s"):
        if row.get(name) is None:
            raise ValueError(f"many-users row has no {name}")
    return Member(
        request=latency.from_row(row, path="many users", arm=arm_of(row)),
        users=int(row["users"]),
        wave=int(row["wave"]),
        wall_s=float(row["wave_wall_s"]),
        prompt_tokens=_prompt_tokens(row),
    )


def cells(rows: Sequence[Dict[str, Any]]) -> Dict[Tuple[int, str, int], WaveCell]:
    """Every cell the rows hold: one per prompt size, arm and user count, in first-seen order."""
    out: Dict[Tuple[int, str, int], WaveCell] = {}
    for row in rows:
        member = from_row(row)
        key = (member.size, member.arm, member.users)
        if key not in out:
            out[key] = WaveCell(size=member.size, arm=member.arm, users=member.users)
        out[key].add(member)
    return out


def sort_cells(cells: Sequence[WaveCell]) -> List[WaveCell]:
    """Prompt size, then user count, then the fixed arm order: the Mac alone before the helper."""
    rank = {name: index for index, name in enumerate(ordered_arms(cell.arm for cell in cells))}
    return sorted(cells, key=lambda cell: (cell.size, cell.users, rank[cell.arm]))


def comparison(cell: WaveCell, base: WaveCell) -> float:
    """How many times shorter the cell's whole wave is than the baseline cell's, for the same cell."""
    return base.mean_wall_s / cell.mean_wall_s


def ask_text(cell: WaveCell) -> str:
    """One cell named for a sentence: 'Mac alone at 4K with 2 users'."""
    return f"{arm_label(cell.arm)} at {size_label(cell.size)} with {cell.users} users"


def reading_line(members: Sequence[Member]) -> str:
    """One sentence on the cold cache and the answers, counted from the rows."""
    requests: List[latency.Request] = [member.request for member in members]
    total = len(requests)
    cold = sum(1 for request in requests if request.cached_tokens == 0)
    answered = [request for request in requests if request.correct is not None]
    right = sum(1 for request in answered if request.correct)
    if cold == total and len(answered) == total and right == total:
        return f"All {total} requests read their prompt cold and got a correct answer."
    if cold == total:
        return f"Every request read its prompt cold; {right} of {len(answered)} answers were correct."
    return f"{cold} of {total} requests read their prompt cold; {right} of {len(answered)} answers were correct."


def failed_marks(members: Sequence[Member]) -> Dict[str, int]:
    """How many rows each failed check marks, over the rows a flag marks not valid."""
    counts: Dict[str, int] = {}
    for member in members:
        for name in member.request.failed:
            counts[name] = counts.get(name, 0) + 1
    return counts
