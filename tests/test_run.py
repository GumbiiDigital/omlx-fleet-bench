"""Tests for the speed runner: settings, helper state and the row it writes."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from unittest.mock import patch

from bench import run
from bench.helper import HelperWaitPolicy
from bench.matrix import load_and_expand, load_matrix, settings_fields_touched

REPO = Path(__file__).resolve().parents[1]
MATRIX = str(REPO / "matrices" / "m3-ultra-a-helper-ready.json")


class FakeClient:
    """Answers like the admin API, and records the helper reads."""

    def __init__(self, helper_states: Optional[List[Any]] = None) -> None:
        self.helper_states = list(helper_states or [{"state": "ready"}])
        self.helper_reads = 0
        self.size = 0

    def apply_settings(self, model: str, desired: Dict[str, Any], fields: List[str]) -> None:
        return None

    def get_prefill_helper_state(self, model: str) -> Any:
        self.helper_reads += 1
        if len(self.helper_states) > 1:
            return self.helper_states.pop(0)
        return self.helper_states[0]

    def start_benchmark(self, model: str, prompt_length: int) -> str:
        self.size = prompt_length
        return "bench-1"

    def poll_results(self, bench_id: str) -> Dict[str, Any]:
        return {
            "status": "completed",
            "results": [{"pp": self.size, "ttft_ms": 1000, "processing_tps": 1000.0}],
        }

    def read_stream_terminal_event(self, bench_id: str) -> Dict[str, Any]:
        return {"type": "upload_skipped", "features": [{"key": "prefill_accelerator"}]}


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "out.jsonl"
        self.matrix = load_matrix(MATRIX)
        self.specs = load_and_expand(MATRIX, only_cells=["gpu:1024", "spark:32768"])[:2]

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            machine="test",
            matrix=MATRIX,
            helper_node="",
            server_log=str(self.dir / "missing.log"),
        )

    def _run(self, client: FakeClient, policy: HelperWaitPolicy) -> List[Dict[str, Any]]:
        fields = settings_fields_touched(self.specs, self.matrix["base_settings"])
        log = {"bench-1": {"cached_tokens": 0, "ane_mlp_operations": 0}}
        with patch("bench.run.read_server_log_since", lambda path, offset: log):
            run._run_specs(
                self._args(),
                cast(Any, client),
                self.specs,
                self.matrix["base_settings"],
                fields,
                6,
                self.out,
                {},
                policy,
            )
        return [json.loads(line) for line in self.out.read_text(encoding="utf-8").splitlines()]

    def test_rows_record_the_helper_state_and_the_wait(self) -> None:
        client = FakeClient([{"state": "ready"}])
        rows = self._run(client, HelperWaitPolicy(timeout_s=30.0))
        self.assertEqual([row["variant"] for row in rows], ["gpu", "spark"])
        self.assertIsNone(rows[0]["helper_state"])
        self.assertEqual(rows[0]["helper_wait_s"], 0.0)
        self.assertEqual(rows[1]["helper_state"], "ready")
        self.assertEqual(rows[1]["helper_wait_s"], 0.0)
        self.assertTrue(rows[1]["validity"]["helper_ready_at_start"])
        self.assertTrue(rows[1]["validity"]["valid"])

    def test_a_helper_row_that_started_before_the_session_is_not_valid(self) -> None:
        client = FakeClient([{"state": "starting"}])
        rows = self._run(client, HelperWaitPolicy(timeout_s=0.0))
        self.assertEqual(rows[1]["helper_state"], "starting")
        self.assertFalse(rows[1]["validity"]["helper_ready_at_start"])
        self.assertFalse(rows[1]["validity"]["valid"])

    def test_no_wait_reads_the_state_once_and_still_records_it(self) -> None:
        client = FakeClient([{"state": "starting"}])
        rows = self._run(client, HelperWaitPolicy(wait=False))
        self.assertEqual(client.helper_reads, 1)
        self.assertEqual(rows[1]["helper_state"], "starting")
        self.assertEqual(rows[1]["helper_wait_s"], 0.0)
        self.assertFalse(rows[1]["validity"]["valid"])

    def test_an_unreadable_state_is_recorded_as_unknown(self) -> None:
        class Broken(FakeClient):
            def get_prefill_helper_state(self, model: str) -> Any:
                raise OSError("HTTP Error 500: Server Error")

        rows = self._run(Broken(), HelperWaitPolicy(timeout_s=0.0))
        self.assertEqual(rows[1]["helper_state"], "unknown")
        self.assertFalse(rows[1]["validity"]["helper_ready_at_start"])


if __name__ == "__main__":
    unittest.main()
