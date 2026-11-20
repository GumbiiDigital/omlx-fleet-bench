#!/usr/bin/env python3
"""Check reader text for the rules a person reading the pages depends on.

Rule 1: a table in a reader page has five columns or fewer. Full tables live in `reports/`.
Rule 2: the hard words of the engine are not used. Plain words instead: "arm" -> setup or round,
"variant" -> setup, "wave" -> group, "cell" -> prompt size and user count, "matrix" -> what was run,
"harness" -> the runner, "sweep" -> prompt-size test, "TTFT" -> wait for the first word,
"prefill" -> reading the prompt, "quant" -> 4-bit, "ANE" -> Apple Neural Engine, "Wilson" -> 95% range.
Rule 3: a word that carries an underscore is a machine name, not prose; say what it means instead.
Rule 4: the results labels `m3-ultra-a` and `m3-ultra-b` never reach a reader; use the display name.
Rule 5: a list holds eight bullets at most, so a page is not a wall of notes.

Two engine names are allowed once per page, and only in brackets after the plain words: the first
time a page says "4-bit prompt memory (Affine4)" it teaches the name, and after that the plain words
alone. A second mention is a fault, because the page has already done that job.

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
from typing import Dict, List, Optional, Sequence, Tuple

# The most columns a reader-page table may have.
MAX_TABLE_COLUMNS = 5
# The most bullets one list may hold before the page turns into a wall of notes.
MAX_BULLETS = 8

# Words the design bans from reader text, with the plain word to use instead. Whole word,
# case-insensitive. The list is data, so a new word is one line here and nothing else changes.
BANNED_WORDS: Tuple[Tuple[str, str], ...] = (
    ("ablation", "a plain comparison"),
    ("ane", "Apple Neural Engine"),
    ("arm", "setup or round"),
    ("cell", "prompt size and user count"),
    ("ctx", "prompt size"),
    ("harness", "the runner"),
    ("http", "say what happened, not a status code"),
    ("jsonl", "row file"),
    ("matrix", "what was run"),
    ("p50", "the middle value"),
    ("p95", "the slow tail"),
    ("prefill", "reading the prompt"),
    ("quant", "4-bit"),
    ("sweep", "prompt-size test"),
    ("ttft", "wait for the first word"),
    ("variant", "setup"),
    ("wave", "group"),
    ("wilson", "95% range"),
)

# The same word in the plural is a different whole word, so it needs its own line.
PLURALS = {"arm": "arms", "cell": "cells", "variant": "variants", "wave": "waves"}

# The engine's own name for a compressed prompt memory: allowed once per page, in brackets.
BRACKETED_ONCE: Dict[str, str] = {
    "affine4": "4-bit prompt memory",
    "affine8": "8-bit prompt memory",
}
_BRACKETED_PATTERN = re.compile(r"\b(?P<word>" + "|".join(BRACKETED_ONCE) + r")\b", re.IGNORECASE)
PARENTHESISED = re.compile(r"\([^()\n]*\)")

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

# A field name or a results label is a machine's word, not a reader's: an underscore or one of the
# two machine labels never belongs in prose.
UNDERSCORE_WORD = re.compile(r"\b\w*_\w*\b")
MACHINE_LABEL = re.compile(r"\bm3-ultra-[ab]\b", re.IGNORECASE)
BULLET = re.compile(r"^\s*[-*+]\s+\S")

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


def _in_brackets(line: str, start: int, end: int) -> bool:
    """True when the span sits inside a pair of brackets on this line."""
    return any(match.start() < start and end <= match.end() for match in PARENTHESISED.finditer(line))


def _bracketed_name(number: int, line: str, seen: Dict[str, int]) -> List[Problem]:
    """The engine names that are allowed once per page, in brackets after the plain words.

    The first mention has to teach the name; a later one has to leave it out. So one mention gets
    one problem, not two.
    """
    problems: List[Problem] = []
    for match in _BRACKETED_PATTERN.finditer(line):
        word = match.group("word").lower()
        first_use = seen.get(word, 0) == 0
        seen[word] = seen.get(word, 0) + 1
        if not first_use:
            problems.append(
                Problem(
                    number,
                    f"'{match.group('word')}' is already named on this page; write {BRACKETED_ONCE[word]}",
                )
            )
        elif not _in_brackets(line, match.start(), match.end()):
            problems.append(
                Problem(
                    number,
                    f"'{match.group('word')}' needs the plain words first: write "
                    f"{BRACKETED_ONCE[word]} ({match.group('word')}) once per page",
                )
            )
    return problems


def _machine_words(number: int, line: str) -> List[Problem]:
    """A field name or a results label in prose: say what it means, or use the display name."""
    problems = [
        Problem(number, f"field name '{match.group(0)}' has an underscore; say what it means in plain words")
        for match in UNDERSCORE_WORD.finditer(line)
    ]
    problems += [
        Problem(number, f"machine label '{match.group(0)}'; use the display name Mac A or Mac B")
        for match in MACHINE_LABEL.finditer(line)
    ]
    return problems


def _bullet_walls(prose: Sequence[Tuple[int, str]]) -> List[Problem]:
    """A list of more than `MAX_BULLETS` bullets in a row, reported once at its first line."""
    problems: List[Problem] = []
    start: Optional[int] = None
    count = 0
    for number, line in prose:
        if BULLET.match(line):
            if count == 0:
                start = number
            count += 1
            if count == MAX_BULLETS + 1 and start is not None:
                problems.append(
                    Problem(
                        start,
                        f"a list of more than {MAX_BULLETS} bullets; split it under small headings",
                    )
                )
            continue
        if line.strip() and line[:1] in (" ", "\t"):
            continue  # the wrapped second line of the bullet above it
        start, count = None, 0
    return problems


def check(markdown_text: str) -> List[Problem]:
    """Every problem in `markdown_text`: a table too wide, a hard word, a list too long."""
    problems: List[Problem] = []
    table_start: Optional[int] = None
    widest = 0
    in_table = False
    seen_names: Dict[str, int] = {}

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
        problems += _bracketed_name(number, line, seen_names)
        problems += _machine_words(number, line)
    close_table()
    problems += _bullet_walls(prose)
    problems.sort(key=lambda problem: problem.line)
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
