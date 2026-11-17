#!/usr/bin/env python3
"""Run a speed matrix against the oMLX admin API and append one JSONL row per run.

Usage:
    python3 bench/run.py --matrix matrices/m3-ultra-spark.json --base-url http://127.0.0.1:8004 \
        --settings ~/.omlx/settings.json --server-log ~/.omlx/logs/server.log \
        --helper-node NODE_ID --machine my-mac --out results/my-mac/speed-DATE.jsonl

Every run is private: the benchmark is started with `align_prompt_to_ane` on, so the
server ends it with `upload_skipped` and nothing goes to the public leaderboard.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bench.client import (  # noqa: E402
    OMLXClient,
    extract_result_metrics,
    feature_keys,
    load_api_key,
)
from bench.collect import read_server_log_since  # noqa: E402
from bench.matrix import SETTING_FIELDS, load_and_expand, load_matrix, settings_fields_touched  # noqa: E402
from bench.validity import assess_validity  # noqa: E402

logger = logging.getLogger("bench.run")


def parse_only_cells(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]


def format_dry_run_line(index: int, spec: Any, settings: Dict[str, Any]) -> str:
    keys = {k: settings.get(k) for k in SETTING_FIELDS if k in settings}
    return (
        f"{index:04d} repeat={spec.repeat_index} variant={spec.variant} "
        f"size={spec.prompt_size} model={spec.model} settings={json.dumps(keys, sort_keys=True)}"
    )


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _log_size(path: str) -> int:
    """Current byte size of the server log (start offset for this run)."""
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def run_matrix(args: argparse.Namespace) -> int:
    matrix = load_matrix(args.matrix)
    base_settings = dict(matrix.get("base_settings") or {})
    specs = load_and_expand(args.matrix, only_cells=parse_only_cells(args.only_cells))
    fields = settings_fields_touched(specs, base_settings)

    if args.dry_run:
        for i, spec in enumerate(specs, start=1):
            merged = spec.merge_settings(base_settings, args.helper_node or "")
            print(format_dry_run_line(i, spec, merged))
        print(f"Total runs: {len(specs)}")
        return 0

    api_key = load_api_key(args.settings)
    client = OMLXClient(args.base_url, api_key)
    client.login()

    out_path = Path(args.out)

    runs_per_cell = int(matrix.get("runs_per_cell", 3))

    with client.preserved_settings(matrix["model"], fields) as original:
        _run_specs(args, client, specs, base_settings, fields, runs_per_cell, out_path, original)
    return 0


def _run_specs(
    args: argparse.Namespace,
    client: OMLXClient,
    specs: List[Any],
    base_settings: Dict[str, Any],
    fields: List[str],
    runs_per_cell: int,
    out_path: Path,
    original: Dict[str, Any],
) -> None:
    """Run each spec; settings are restored once by the caller."""
    for spec in specs:
        desired = spec.merge_settings(base_settings, args.helper_node or "")
        row_base: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "machine": args.machine,
            "matrix": str(Path(args.matrix)),
            "model": spec.model,
            "variant": spec.variant,
            "prompt_size": spec.prompt_size,
            "repeat_index": spec.repeat_index,
            "runs_per_cell": runs_per_cell,
            "helper_on": spec.helper_on,
            "ane_on": spec.ane_on,
            "desired_settings": {k: desired.get(k) for k in fields},
        }
        bench_id: Optional[str] = None
        try:
            row_base["settings_before"] = original
            client.apply_settings(spec.model, desired, fields)
            log_offset = _log_size(args.server_log)
            bench_id = client.start_benchmark(spec.model, spec.prompt_size)
            row_base["bench_id"] = bench_id
            poll = client.poll_results(bench_id)
            stream_event = client.read_stream_terminal_event(bench_id)
            metrics = extract_result_metrics(poll, spec.prompt_size)
            parsed = read_server_log_since(args.server_log, log_offset).get(bench_id, {})
            end_type = str(stream_event.get("type") or stream_event.get("event") or "")
            feats = feature_keys(stream_event)
            validity = assess_validity(
                status=str(poll.get("status", "")),
                end_event_type=end_type,
                feature_keys=feats,
                helper_on=spec.helper_on,
                ane_on=spec.ane_on,
                log_parsed=parsed,
            )
            row = {
                **row_base,
                "status": poll.get("status"),
                "end_event_type": end_type,
                "feature_keys": feats,
                "metrics": metrics,
                "log": parsed,
                "validity": validity,
            }
        except Exception as exc:  # noqa: BLE001 — record row then continue
            logger.exception("Run failed for %s", spec.cell_key)
            row = {
                **row_base,
                "bench_id": bench_id,
                "error": str(exc),
                "validity": {"valid": False},
            }

        append_jsonl(out_path, row)
        logger.info(
            "Wrote %s valid=%s",
            bench_id or "failed",
            row.get("validity", {}).get("valid"),
        )



def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="oMLX fleet benchmark runner")
    parser.add_argument("--matrix", required=True, help="Path to matrix JSON")
    parser.add_argument("--base-url", required=True, help="oMLX admin base URL")
    parser.add_argument("--settings", required=True, help="oMLX settings.json path")
    parser.add_argument("--server-log", required=True, help="Local server.log path")
    parser.add_argument("--helper-node", default="", help="Spark helper node id")
    parser.add_argument("--out", required=True, help="JSONL output path")
    parser.add_argument("--machine", required=True, help="Machine label for results")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    parser.add_argument(
        "--only-cells",
        default=None,
        help="Comma-separated variant:size filters",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return run_matrix(args)


if __name__ == "__main__":
    raise SystemExit(main())