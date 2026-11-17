"""Quality tasks for oMLX settings: passkey retrieval, GSM8K, MMLU.

Prompt building and scoring only; no network. Everything here is deterministic so a
row can be re-checked later.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

LETTERS = "ABCD"

# Neutral filler for the passkey task. Repeating it keeps the prompt reproducible
# while the needle sits at a fixed depth.
FILLER = (
    "The workshop keeps its records in plain language and reads them once a week. "
    "Each page lists a date, a short note about the tools used, and the name of the "
    "person who checked the work. Nothing on a page changes after the check, so an "
    "old page still matches the shelf it came from. The staff copy a line only when "
    "a visitor asks for it, and they write the request in the same book. "
)

NEEDLE_TEMPLATE = "The passkey for this record is {needle}."

PASSKEY_QUESTION = (
    "Question: what is the passkey in the record above? "
    "Answer with the number only."
)

GSM8K_INSTRUCTION = (
    "Solve the problem below. Show no reasoning in the final line. "
    "End with a line in the form: #### <number>"
)

MMLU_INSTRUCTION = "Answer with the letter of the correct choice only."


def _words(text: str) -> int:
    return len(text.split())


CACHE_TAG_TEMPLATE = "Request tag: {tag}. Ignore this line."


def build_passkey_prompt(
    target_tokens: int,
    needle: str,
    *,
    depth: float = 0.5,
    tokens_per_word: float = 1.11,
    cache_tag: str = "",
) -> str:
    """Build a filler prompt of about `target_tokens` tokens with the needle at `depth`.

    A non-empty `cache_tag` adds one line at the very start. Identical prompt text made the
    server serve later variants from its prompt cache, so the long read was never fresh.
    The tag changes the leading bytes only; the body, needle and question stay the same.
    """
    if not 0.0 <= depth <= 1.0:
        raise ValueError("depth must be between 0 and 1")
    target_words = max(_words(FILLER), int(target_tokens / tokens_per_word))
    repeats = max(1, target_words // _words(FILLER))
    body = FILLER * repeats
    words = body.split()

    needle_text = NEEDLE_TEMPLATE.format(needle=needle)
    insert_at = max(1, min(len(words) - 1, int(len(words) * depth)))
    head = " ".join(words[:insert_at])
    tail = " ".join(words[insert_at:])
    prompt = f"{head}\n{needle_text}\n{tail}\n\n{PASSKEY_QUESTION}"
    if not cache_tag:
        return prompt
    return f"{CACHE_TAG_TEMPLATE.format(tag=cache_tag)}\n\n{prompt}"


def approximate_tokens(text: str, tokens_per_word: float = 1.11) -> int:
    """Rough token count, used only to size a prompt before the server reports the real one."""
    return int(_words(text) * tokens_per_word)


def _normalize_number(text: str) -> Optional[float]:
    cleaned = text.strip().replace(",", "").replace("$", "").replace("%", "").rstrip(".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def last_number(text: str) -> Optional[float]:
    """Last number in a string, as a float. Trailing punctuation and separators ignored."""
    matches = NUMBER_RE.findall(text or "")
    if not matches:
        return None
    return _normalize_number(matches[-1])


def reference_final_number(answer: str) -> Optional[float]:
    """GSM8K reference answers end with '#### <number>'."""
    if "####" in answer:
        return last_number(answer.split("####")[-1])
    return last_number(answer)


def model_final_number(content: str) -> Optional[float]:
    """Final number from a model reply: after '####' when present, else the last number."""
    if not content:
        return None
    if "####" in content:
        return last_number(content.split("####")[-1])
    return last_number(content)


def score_gsm8k(content: str, reference: str) -> Dict[str, Any]:
    expected = reference_final_number(reference)
    got = model_final_number(content)
    ok = expected is not None and got is not None and abs(expected - got) < 1e-6
    return {"expected": expected, "got": got, "correct": ok}


def format_mmlu_prompt(question: str, choices: Sequence[str], subject: str = "") -> str:
    if len(choices) != 4:
        raise ValueError("MMLU needs exactly 4 choices")
    lines = [f"The following is a multiple choice question about {subject or 'a subject'}.".strip(), ""]
    lines.append(question.strip())
    lines.append("")
    for letter, choice in zip(LETTERS, choices):
        lines.append(f"{letter}. {choice.strip()}")
    lines.append("")
    lines.append(MMLU_INSTRUCTION)
    return "\n".join(lines)


LABELLED_ANSWER_RE = re.compile(
    r"(?:answer|choice|option)\s*(?:is|:)?\s*\(?([ABCD])\)?", re.IGNORECASE
)
BARE_ANSWER_RE = re.compile(r"^\s*\(?([ABCD])\)?\s*(?:[.)]|$)", re.IGNORECASE)
ANY_LETTER_RE = re.compile(r"\b([ABCD])\b")


def extract_letter(content: str) -> Optional[str]:
    """Letter from a reply: a labelled answer first, then a bare letter, then any letter."""
    text = (content or "").strip()
    if not text:
        return None
    labelled = LABELLED_ANSWER_RE.search(text)
    if labelled:
        return labelled.group(1).upper()
    bare = BARE_ANSWER_RE.match(text)
    if bare:
        return bare.group(1).upper()
    any_letter = ANY_LETTER_RE.search(text)
    if any_letter:
        return any_letter.group(1).upper()
    return None


def score_mmlu(content: str, answer_index: int) -> Dict[str, Any]:
    expected = LETTERS[answer_index]
    got = extract_letter(content)
    return {"expected": expected, "got": got, "correct": got == expected}


def score_passkey(content: str, needle: str) -> Dict[str, Any]:
    digits = re.sub(r"\D", "", content or "")
    return {"expected": needle, "got": digits or None, "correct": needle in digits}


def prompt_messages(prompt: str, system: Optional[str] = None) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def gsm8k_prompt(question: str) -> str:
    return f"{GSM8K_INSTRUCTION}\n\nProblem: {question.strip()}"


def summarize_task(rows: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
    """Return (correct, total) over rows that carry a score."""
    scored = [r for r in rows if "correct" in r]
    return sum(1 for r in scored if r["correct"]), len(scored)
