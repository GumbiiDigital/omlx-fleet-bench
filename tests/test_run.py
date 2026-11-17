"""Tests for the speed runner: the order of calls and the row it writes."""

import argparse
import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from unittest.mock import patch

from bench import run
from bench.chat import ChatError
from bench.helper import HelperWaitPolicy
from bench.matrix import load_and_expand, load_matrix, settings_fields_touched

REPO = Path(__file__).resolve().parents[1]
MATRIX = str(REPO / "matrices" / "m3-ultra-a-helper-ready.json")

READY = {"state": "ready", "since": 10.0, "layers": 49, "held": 63}


def proof(at: Optional[float], *, state: str = "ready") -> Dict[str, Any]:
    payload: Dict[str, Any] = {"state": state, "since": 10.0, "layers": 49, "held": 63}
    if at is not None:
        payload["last_prompt"] = {"tokens": 32768, "seconds": 26.04, "at": at}
    return payload


class FakeClient:
    """Answers like the admin API, and records what the runner did, in order."""

    def __init__(self, helper_states: Optional[List[Any]] = None, order: Optional[List[str]] = None) -> None:
        self.helper_states = list(helper_states or [READY])
        self.helper_reads = 0
        self.order = order if order is not None else []
        self.size = 0

    def apply_settings(self, model: str, desired: Dict[str, Any], fields: List[str]) -> None:
        self.order.append("settings")

    def get_prefill_helper_state(self, model: str) -> Any:
        self.order.append("read")
        self.helper_reads += 1
        if len(self.helper_states) > 1:
            return self.helper_states.pop(0)
        return self.helper_states[0]

    def start_benchmark(self, model: str, prompt_length: int) -> str:
        self.order.append("request")
        self.size = prompt_length
        return "bench-1"

    def poll_results(self, bench_id: str) -> Dict[str, Any]:
        return {
            "status": "completed",
            "results": [{"pp": self.size, "ttft_ms": 1000, "processing_tps": 1000.0}],
        }

    def read_stream_terminal_event(self, bench_id: str) -> Dict[str, Any]:
        return {"type": "upload_skipped", "features": [{"key": "prefill_accelerator"}]}


class FakeChat:
    """Stands in for the model probe."""

    def __init__(self, order: Optional[List[str]] = None, error: Optional[ChatError] = None) -> None:
        self.order = order if order is not None else []
        self.error = error

    def wait_until_ready(
        self, model: str, *, timeout_s: float = 600.0, interval_s: float = 5.0
    ) -> Dict[str, Any]:
        self.order.append("probe")
        if self.error:
            raise self.error
        return {"content": "pong"}


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
            ready_timeout=600.0,
        )

    def _run(
        self,
        client: FakeClient,
        chat: FakeChat,
        policy: Optional[HelperWaitPolicy] = None,
    ):
        policy = policy or HelperWaitPolicy(timeout_s=0.0, stable_s=0.0)
        fields = settings_fields_touched(self.specs, self.matrix["base_settings"])
        log = {"bench-1": {"cached_tokens": 0, "ane_mlp_operations": 0}}
        with patch("bench.run.read_server_log_since", lambda path, offset: log):
            code = run._run_specs(
                self._args(),
                cast(Any, client),
                cast(Any, chat),
                self.specs,
                self.matrix["base_settings"],
                fields,
                6,
                self.out,
                {},
                policy,
            )
        rows = [json.loads(line) for line in self.out.read_text(encoding="utf-8").splitlines()]
        return code, rows

    def test_the_order_is_settings_probe_read_request_proof(self) -> None:
        order: List[str] = []
        client = FakeClient([READY], order=order)
        chat = FakeChat(order=order)
        code, _ = self._run(client, chat)
        self.assertEqual(code, 0)
        self.assertEqual(
            order,
            [
                "settings", "probe", "request",              # helper off: no state to read
                "settings", "probe", "read", "request", "read",
            ],
        )

    def test_rows_record_the_helper_state_and_the_wait(self) -> None:
        client, chat = FakeClient([READY, proof(time.time() + 60)]), FakeChat()
        _, rows = self._run(client, chat)
        self.assertEqual([row["variant"] for row in rows], ["gpu", "spark"])
        self.assertIsNone(rows[0]["helper_state"])
        self.assertEqual(rows[0]["helper_wait_s"], 0.0)
        self.assertIsNone(rows[0]["helper_layers"])
        self.assertIsNone(rows[0]["helper_last_prompt_at"])
        self.assertEqual(rows[1]["helper_state"], "ready")
        self.assertEqual(rows[1]["helper_wait_s"], 0.0)
        self.assertTrue(rows[1]["validity"]["helper_ready_at_start"])
        self.assertTrue(rows[1]["validity"]["valid"])

    def test_the_proof_fields_are_recorded(self) -> None:
        client, chat = FakeClient([READY, proof(time.time() + 60)]), FakeChat()
        _, rows = self._run(client, chat)
        row = rows[1]
        self.assertEqual(row["helper_layers"], 49)
        self.assertEqual(row["helper_held"], 63)
        self.assertEqual(row["helper_session_since"], 10.0)
        self.assertEqual(row["helper_last_prompt_tokens"], 32768)
        self.assertEqual(row["helper_last_prompt_seconds"], 26.04)
        self.assertIsNotNone(row["helper_last_prompt_at"])
        self.assertTrue(row["validity"]["helper_served"])

    def test_a_row_the_helper_did_not_serve_is_not_valid(self) -> None:
        client, chat = FakeClient([READY, proof(time.time() - 3600)]), FakeChat()
        _, rows = self._run(client, chat)
        self.assertFalse(rows[1]["validity"]["helper_served"])
        self.assertFalse(rows[1]["validity"]["valid"])

    def test_an_unreadable_proof_leaves_the_row_unfailed(self) -> None:
        client, chat = FakeClient([READY, proof(None)]), FakeChat()
        _, rows = self._run(client, chat)
        self.assertIsNone(rows[1]["validity"]["helper_served"])
        self.assertTrue(rows[1]["validity"]["valid"])

    def test_a_helper_row_that_started_before_the_session_is_not_valid(self) -> None:
        client = FakeClient([{"state": "starting"}, proof(time.time() + 60)])
        chat = FakeChat()
        _, rows = self._run(client, chat, HelperWaitPolicy(timeout_s=0.0))
        self.assertEqual(rows[1]["helper_state"], "starting")
        self.assertFalse(rows[1]["validity"]["helper_ready_at_start"])
        self.assertFalse(rows[1]["validity"]["valid"])

    def test_a_ready_state_the_wait_did_not_trust_is_not_valid(self) -> None:
        client, chat = FakeClient([READY, proof(time.time() + 60)]), FakeChat()
        _, rows = self._run(client, chat, HelperWaitPolicy(timeout_s=0.0, stable_s=10.0))
        self.assertEqual(rows[1]["helper_state"], "ready")
        self.assertFalse(rows[1]["validity"]["helper_ready_at_start"])
        self.assertFalse(rows[1]["validity"]["valid"])

    def test_no_wait_reads_once_at_the_start_and_once_after(self) -> None:
        client = FakeClient([{"state": "starting"}, proof(time.time() + 60)])
        chat = FakeChat()
        _, rows = self._run(client, chat, HelperWaitPolicy(wait=False))
        self.assertEqual(client.helper_reads, 2)
        self.assertEqual(rows[1]["helper_state"], "starting")
        self.assertEqual(rows[1]["helper_wait_s"], 0.0)
        self.assertFalse(rows[1]["validity"]["valid"])

    def test_an_unreadable_state_is_recorded_as_unknown(self) -> None:
        class Broken(FakeClient):
            def get_prefill_helper_state(self, model: str) -> Any:
                raise OSError("HTTP Error 500: Server Error")

        client, chat = Broken(), FakeChat()
        _, rows = self._run(client, chat)
        self.assertEqual(rows[1]["helper_state"], "unknown")
        self.assertFalse(rows[1]["validity"]["helper_ready_at_start"])
        self.assertIsNone(rows[1]["validity"]["helper_served"])

    def test_a_probe_that_never_answers_writes_a_row_and_stops(self) -> None:
        client = FakeClient([READY])
        chat = FakeChat(error=ChatError("model 'm' did not answer a probe within 600s: busy"))
        code, rows = self._run(client, chat)
        self.assertEqual(code, 1)
        self.assertEqual(len(rows), 1)
        self.assertIn("did not answer a probe", rows[0]["error"])
        self.assertFalse(rows[0]["validity"]["valid"])


if __name__ == "__main__":
    unittest.main()
