#!/usr/bin/env python3
"""Build the fixed quality data files used by matrices/quality.json.

Two files, both deterministic so a run can be reproduced months later:

    data/gsm8k-200.jsonl   200 questions from the GSM8K test split
    data/mmlu-500.jsonl    500 questions, 25 from each of 20 MMLU subjects

Sources
    GSM8K: https://github.com/openai/grade-school-math (MIT). Pass a local copy of
           test.jsonl with --gsm8k-source, or let the script fetch the raw file.
    MMLU:  https://huggingface.co/datasets/cais/mmlu (MIT). Rows are read through the
           Hugging Face datasets-server JSON API, so no extra packages are needed.

Usage:
    python3 scripts/fetch_quality_data.py                     # write both files
    python3 scripts/fetch_quality_data.py --gsm8k-only
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

CERT_HINT = "pass --ca-bundle /etc/ssl/cert.pem when the Python install has no certificate store"

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

GSM8K_RAW = (
    "https://raw.githubusercontent.com/openai/grade-school-math/master/"
    "grade_school_math/data/test.jsonl"
)
MMLU_ROWS = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=cais%2Fmmlu&config={config}&split=test&offset={offset}&length={length}"
)

GSM8K_COUNT = 200
MMLU_PER_SUBJECT = 25
MMLU_SUBJECTS = [
    "abstract_algebra",
    "anatomy",
    "astronomy",
    "business_ethics",
    "clinical_knowledge",
    "college_biology",
    "college_chemistry",
    "college_computer_science",
    "college_mathematics",
    "college_physics",
    "computer_security",
    "conceptual_physics",
    "econometrics",
    "electrical_engineering",
    "elementary_mathematics",
    "formal_logic",
    "high_school_biology",
    "high_school_chemistry",
    "high_school_mathematics",
    "high_school_physics",
]


def fetch(url: str, ca_bundle: str | None = None) -> bytes:
    """Read a URL. `ca_bundle` (or SSL_CERT_FILE) is used when the Python build ships no CA store."""
    bundle = ca_bundle or os.environ.get("SSL_CERT_FILE")
    context = ssl.create_default_context(cafile=bundle) if bundle else None
    try:
        with urllib.request.urlopen(url, timeout=120, context=context) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot read {url}: {exc}. If this is a certificate error, {CERT_HINT}") from exc




def read_jsonl_text(text: str) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build_gsm8k(source: Path | None, ca_bundle: str | None = None) -> List[Dict[str, Any]]:
    if source is not None:
        rows = read_jsonl_text(source.read_text(encoding="utf-8"))
    else:
        rows = read_jsonl_text(fetch(GSM8K_RAW, ca_bundle).decode("utf-8"))
    if len(rows) < GSM8K_COUNT:
        raise SystemExit(f"GSM8K source has only {len(rows)} rows")
    step = (len(rows) - 1) / (GSM8K_COUNT - 1)
    picked = sorted({int(round(i * step)) for i in range(GSM8K_COUNT)})
    out: List[Dict[str, Any]] = []
    for index in picked:
        row = rows[index]
        out.append(
            {
                "id": f"gsm8k-{index:04d}",
                "source_index": index,
                "question": row["question"],
                "answer": row["answer"],
            }
        )
    return out


def build_mmlu(ca_bundle: str | None = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for subject in MMLU_SUBJECTS:
        url = MMLU_ROWS.format(config=subject, offset=0, length=MMLU_PER_SUBJECT)
        payload = json.loads(fetch(url, ca_bundle).decode("utf-8"))
        rows = payload.get("rows") or []
        if len(rows) < MMLU_PER_SUBJECT:
            raise SystemExit(f"MMLU subject {subject} returned {len(rows)} rows")
        for item in rows:
            row = item["row"]
            out.append(
                {
                    "id": f"mmlu-{subject}-{item['row_idx']:05d}",
                    "subject": row["subject"],
                    "question": row["question"],
                    "choices": row["choices"],
                    "answer": int(row["answer"]),
                }
            )
    return out


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {path}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gsm8k-source", type=Path, default=None)
    parser.add_argument("--ca-bundle", default=None, help="PEM file for TLS checks")
    parser.add_argument("--gsm8k-only", action="store_true")
    parser.add_argument("--mmlu-only", action="store_true")
    args = parser.parse_args(argv)

    if not args.mmlu_only:
        write_jsonl(DATA_DIR / "gsm8k-200.jsonl", build_gsm8k(args.gsm8k_source, args.ca_bundle))
    if not args.gsm8k_only:
        write_jsonl(DATA_DIR / "mmlu-500.jsonl", build_mmlu(args.ca_bundle))
    return 0


if __name__ == "__main__":
    sys.exit(main())
