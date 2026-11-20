#!/usr/bin/env python3
"""Check reader text for the two rules a person reading the pages depends on.

Rule 1: a table in a reader page has five columns or fewer. Full tables live in `reports/`.
Rule 2: the hard words of the engine are not used. Plain words instead: "arm" -> setup or round,
"variant" -> setup, "wave" -> group, "cell" -> prompt size and user count, "matrix" -> what was run,
"harness" -> the runner, "sweep" -> prompt-size test, "TTFT" -> wait for the first word,
"prefill" -> reading the prompt, "quant" -> 4-bit.

Word checks skip fenced code blocks, inline code and link targets, because a file name or a command
is not prose. Usage:

    python3 bench/readable.py README.md docs/speed.md
    python3 bench/readable.py README.md && echo "no problems"

Exit code 1 means at least one problem, and every problem is printed as `file:line: message`.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# The most columns a reader-page table may have.
MAX_TABLE_COLUMNS = 5

# Words the design bans from reader text, with the plain word to use instead. Whole word,
# case-insensitive. The list is data, so a new word is one line here and nothing else changes.
BANNED_WORDS: Tuple[Tuple[str, str], ...] = (
    ("ablation", "a plain comparison"),
    ("arm", "setup or round"),
    ("cell", "prompt size and user count"),
    ("ctx", "prompt size"),
    ("harness", "the runner"),
    ("matrix", "what was run"),
    ("p50", "the middle value"),
    ("p95", "the slow tail"),
    ("prefill", "reading the prompt"),
    ("quant", "4-bit"),
    ("sweep", "prompt-size test"),
    ("ttft", "wait for the first word"),
    ("variant", "setup"),
    ("wave", "group"),
)

# The same word in the plural is a different whole word, so it needs its own line.
PLURALS = {"arm": "arms", "cell": "cells", "variant": "variants", "wave": "waves"}

_BANNED = {
    word: plain
    for word, plain in BANNED_WORDS
} | {
    PLURALS[word]: plain for word, plain in BANNED_WORDS if word in PLURALS
}
_BANNED_PATTERN = re.compile(
    r"\b(?P<word>" + "|".join(sorted((re.escape(word) for word in _BANNED), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

FENCE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
INLINE_CODE = re.compile(r"(?P<ticks>`+)(?:(?!`).)+?(?P=ticks)")
LINK_TARGET = re.compile(r"\]\([^)\n]*\)")
REFERENCE_TARGET = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*\S+.*$")
# Only the value of a link attribute is a file name, not prose. The alt and title text of an
# image IS read by a person (and by a screen reader), so it is checked like the rest of the page.
HTML_LINK_ATTRIBUTE = re.compile(
    r'(?P<name>\b(?:href|src|srcset)\s*=\s*)(?P<value>"[^"\n]*"|\'[^\'\n]*\'|[^\s>]+)', re.IGNORECASE
)
BARE_URL = re.compile(r"https?://\S+")
# A generated-block marker and any other HTML comment is plumbing, not text for a person.
HTML_COMMENT = re.compile(r"<!--.*?-->")
# The line under a table header: dashes and colons between pipes, with at least one pipe.
SEPARATOR = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")


@dataclass(frozen=True)
class Problem:
    """One fault in the text, at one line, said in the words a reader would use."""

    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


def _mask(match: "re.Match[str]") -> str:
    """Blank out a span but keep its length, so columns and line numbers do not move."""
    return " " * len(match.group(0))


def _mask_value(match: "re.Match[str]") -> str:
    """Blank out an attribute value and keep the name, so a file name is not read as prose."""
    return match.group("name") + " " * len(match.group("value"))


def _prose(line: str) -> str:
    """The part of a line a reader reads: no inline code, no link target, no URL.

    Alt and title text of an image stays, because that is what a person hears or reads when the
    picture does not load. Only the file names in href, src and srcset are skipped.
    """
    line = INLINE_CODE.sub(_mask, line)
    line = LINK_TARGET.sub(_mask, line)
    line = REFERENCE_TARGET.sub(_mask, line)
    line = HTML_COMMENT.sub(_mask, line)
    line = HTML_LINK_ATTRIBUTE.sub(_mask_value, line)
    return BARE_URL.sub(_mask, line)


def _prose_lines(text: str) -> Tuple[List[Tuple[int, str]], Optional[Problem]]:
    """The lines outside a fenced code block, masked down to prose, and any unclosed block.

    A closing fence has to be bare (no word after it) and at least as long as the one that opened
    the block, which is what a Markdown reader does. An unclosed block is a fault of its own: the
    rest of the page would go unchecked, so the page is said to be broken rather than passing.
    """
    lines: List[Tuple[int, str]] = []
    fence: Optional[str] = None
    opened_at = 0
    for number, line in enumerate(text.splitlines(), start=1):
        marker = FENCE.match(line)
        if fence is None:
            if marker:
                fence, opened_at = marker.group("fence"), number
                continue
            lines.append((number, _prose(line)))
            continue
        closes = (
            marker is not None
            and marker.group("fence")[0] == fence[0]
            and len(marker.group("fence")) >= len(fence)
            and not marker.group("info").strip()
        )
        if closes:
            fence = None
    if fence is None:
        return lines, None
    return lines, Problem(opened_at, f"unclosed code fence; close it with a bare line of {fence}")


def _columns(row: str) -> int:
    """How many cells a Markdown table row has, counted by its unescaped pipes."""
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return len(re.split(r"(?<!\\)\|", body))


def _is_separator(line: str) -> bool:
    """True for the dash line under a table header, the one that makes the rows above a table."""
    return "|" in line and bool(SEPARATOR.match(line))


def check(markdown_text: str) -> List[Problem]:
    """Every problem in `markdown_text`: a table too wide, or a banned word outside code."""
    problems: List[Problem] = []
    table_start: Optional[int] = None
    widest = 0
    in_table = False

    def close_table() -> None:
        nonlocal table_start, widest
        if table_start is not None and widest > MAX_TABLE_COLUMNS:
            problems.append(
                Problem(
                    table_start,
                    f"table has {widest} columns; a reader page allows {MAX_TABLE_COLUMNS} or fewer "
                    f"(the full table belongs in reports/)",
                )
            )
        table_start, widest = None, 0

    prose, fence_problem = _prose_lines(markdown_text)
    if fence_problem is not None:
        problems.append(fence_problem)

    for position, (number, line) in enumerate(prose):
        next_line = prose[position + 1][1] if position + 1 < len(prose) else ""
        # A row is a line that starts with a pipe, the dash line under a header, or a line whose
        # next line is that dash line. A table written without outer pipes is still a table.
        starts_with_pipe = line.strip().startswith("|")
        is_row = (
            starts_with_pipe
            or _is_separator(line)
            or _is_separator(next_line)
            or (in_table and bool(line.strip()) and "|" in line)
        )
        if is_row:
            if table_start is None:
                table_start = number
            widest = max(widest, _columns(line))
            in_table = True
        else:
            close_table()
            in_table = False
        for match in _BANNED_PATTERN.finditer(line):
            word = match.group("word")
            problems.append(
                Problem(number, f"hard word '{word}'; write {_BANNED[word.lower()]} instead")
            )
    close_table()
    return problems


def check_files(paths: Sequence[Path]) -> List[Tuple[Path, Problem]]:
    """Every problem in every file, each with the file it came from."""
    out: List[Tuple[Path, Problem]] = []
    for path in paths:
        for problem in check(path.read_text(encoding="utf-8")):
            out.append((path, problem))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check Markdown for wide tables and hard words")
    parser.add_argument("paths", nargs="+", help="Markdown files to check")
    args = parser.parse_args(argv)
    found = check_files([Path(name) for name in args.paths])
    for path, problem in found:
        print(f"{path}:{problem.line}: {problem.message}")
    if found:
        print(f"readable: {len(found)} problems")
        return 1
    print("readable: no problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
