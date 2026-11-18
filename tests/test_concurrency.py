"""Many users at once: the wave starts together, one row per request, and the flags say so."""

import json
import re
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from bench import chatrows, concurrency, quality
from bench.chat import ChatError
from bench.helper import HelperStatus
from bench.validity import assess_many_users_validity

REPO = Path(__file__).resolve().parents[1]
MATRIX = str(REPO / "matrices" / "m3-ultra-b-many-users.json")
SPEED_MATRIX = REPO / "matrices" / "m3-ultra-b-speed.json"
NEEDLE_RE = re.compile(r"The passkey for this record is (\d+)\.")


def reply(content: str = "4829157", *, cached: Optional[int] = 0) -> Dict[str, Any]:
    """One chat answer as `bench/chat.py` normalizes it."""
    return {
        "content": content,
        "reasoning": "",
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 64, "completion_tokens": 4, "cached_tokens": cached},
        "server_timing": {"time_to_first_token": 0.2, "total_time": 0.4},
        "latency_s": 0.4,
    }


def helper_answer(state: str = "ready", at: Optional[float] = None) -> Dict[str, Any]:
    """One GET /admin/api/prefill-helper/models/<model> answer."""
    answer: Dict[str, Any] = {"state": state, "since": 10.0, "layers": 49, "held": 63}
    if at is not None:
        answer["last_prompt"] = {"tokens": 64, "seconds": 0.02, "at": at}
    return answer


class _FakeAdmin:
    """Records the settings writes, the restore, and answers the helper state reads."""

    def __init__(self, helper_states: Optional[List[Dict[str, Any]]] = None) -> None:
        self.applied: List[Dict[str, Any]] = []
        self.restored = False
        self.helper_reads = 0
        self.helper_states = list(helper_states or [helper_answer("ready", at=time.time() + 600)])

    def login(self) -> None:
        return None

    def get_prefill_helper_state(self, model: str) -> Any:
        self.helper_reads += 1
        if len(self.helper_states) > 1:
            return self.helper_states.pop(0)
        return self.helper_states[0]

    @contextmanager
    def preserved_settings(self, model: str, fields: List[str]) -> Any:
        try:
            yield {field: None for field in fields}
        finally:
            self.restored = True

    def apply_settings(self, model: str, desired: Dict[str, Any], fields: List[str]) -> None:
        self.applied.append({field: desired.get(field) for field in fields})


class _FakeChat:
    """A chat client whose calls open a gate: a call returns only when every user is in flight."""

    def __init__(
        self,
        *,
        parties: int = 1,
        failures: int = 0,
        cached: Optional[int] = 0,
        ready_error: str = "",
    ) -> None:
        self.gate = threading.Barrier(parties, timeout=10) if parties > 1 else None
        self.failures = failures
        self.cached = cached
        self.ready_error = ready_error
        self.messages: List[List[Dict[str, str]]] = []
        self.events: List[str] = []
        self._lock = threading.Lock()

    def wait_until_ready(self, model: str, *, timeout_s: float = 600.0, interval_s: float = 5.0) -> Dict[str, Any]:
        self.events.append("probe")
        if self.ready_error:
            raise ChatError(self.ready_error)
        return {"content": "pong"}

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        if self.gate is not None:
            # Times out unless every request of the wave is in flight at the same moment.
            self.gate.wait()
        with self._lock:
            self.messages.append(messages)
            fail = self.failures > 0
            if fail:
                self.failures -= 1
        if fail:
            raise ChatError("HTTP 409 from chat endpoint: busy; unload pending")
        found = NEEDLE_RE.search(messages[-1]["content"])
        return reply(found.group(1) if found else "0", cached=self.cached)


class MatrixFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = concurrency.load_many_users_matrix(MATRIX)

    def test_matrix_file_loads(self) -> None:
        self.assertEqual(self.matrix["model"], "Qwen3.8-Flash-Next-oQ4e-mtp")
        self.assertEqual([v["name"] for v in self.matrix["variants"]], ["gpu", "spark"])
        self.assertEqual(self.matrix["prompt_sizes"], [4096, 32768])
        self.assertEqual(self.matrix["users"], [1, 2, 4, 8])
        self.assertEqual(self.matrix["waves"], 3)
        self.assertEqual(self.matrix["max_tokens"], 128)
        self.assertEqual(self.matrix["temperature"], 0)

    def test_settings_match_the_speed_matrix(self) -> None:
        speed = json.loads(SPEED_MATRIX.read_text(encoding="utf-8"))
        self.assertEqual(self.matrix["base_settings"], speed["base_settings"])
        mine = {v["name"]: v for v in self.matrix["variants"]}
        theirs = {v["name"]: v for v in speed["variants"]}
        for name in ("gpu", "spark"):
            self.assertEqual(mine[name], theirs[name])

    def test_missing_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.json"
            path.write_text(json.dumps({"model": "m"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                concurrency.load_many_users_matrix(str(path))


class WaveOrderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = concurrency.load_many_users_matrix(MATRIX)

    def test_order_is_size_then_setting_then_users_then_wave(self) -> None:
        plans = concurrency.waves_for(self.matrix, users=[1, 2], waves=2)
        keys = [(p.prompt_size, p.variant.name, p.users, p.wave) for p in plans]
        self.assertEqual(
            keys,
            [
                (4096, "gpu", 1, 0), (4096, "gpu", 1, 1),
                (4096, "gpu", 2, 0), (4096, "gpu", 2, 1),
                (4096, "spark", 1, 0), (4096, "spark", 1, 1),
                (4096, "spark", 2, 0), (4096, "spark", 2, 1),
                (32768, "gpu", 1, 0), (32768, "gpu", 1, 1),
                (32768, "gpu", 2, 0), (32768, "gpu", 2, 1),
                (32768, "spark", 1, 0), (32768, "spark", 1, 1),
                (32768, "spark", 2, 0), (32768, "spark", 2, 1),
            ],
        )

    def test_the_matrix_is_four_blocks_of_twelve_waves(self) -> None:
        plans = concurrency.waves_for(self.matrix)
        self.assertEqual(len(plans), 48)
        self.assertEqual(sum(plan.users for plan in plans), 180)
        self.assertEqual(len(concurrency.blocks_of(plans)), 4)

    def test_wave_ids_are_unique_and_shared(self) -> None:
        plans = concurrency.waves_for(self.matrix)
        ids = [plan.wave_id for plan in plans]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(plans[0].wave_id, "gpu-4096-u1-w0")

    def test_users_override(self) -> None:
        self.assertEqual(len(concurrency.waves_for(self.matrix, users=[8], waves=1)), 4)
        self.assertIsNone(concurrency.parse_users(None))
        self.assertEqual(concurrency.parse_users("1, 4"), [1, 4])
        with self.assertRaises(ValueError):
            concurrency.parse_users("0")


class WaveRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = concurrency.load_many_users_matrix(MATRIX)
        self.plan = concurrency.waves_for(self.matrix, users=[4], waves=2)[0]

    def test_every_request_has_its_own_prompt(self) -> None:
        requests = concurrency.wave_requests(self.plan)
        self.assertEqual([r.index for r in requests], [0, 1, 2, 3])
        firsts = [r.prompt.split("\n", 1)[0] for r in requests]
        self.assertEqual(len(set(firsts)), 4, "two users of one wave share a prompt")
        self.assertEqual(len({r.prompt for r in requests}), 4)
        for request in requests:
            self.assertIn(request.needle, request.prompt)
            self.assertEqual(request.messages[-1]["role"], "user")

    def test_prompts_of_two_waves_never_repeat(self) -> None:
        waves = concurrency.waves_for(self.matrix, users=[4], waves=2)
        prompts = [r.prompt for plan in waves for r in concurrency.wave_requests(plan)]
        self.assertEqual(len(set(prompts)), len(prompts))


class SendWaveTest(unittest.TestCase):
    def test_a_wave_starts_its_requests_together(self) -> None:
        parties = 4
        inner = threading.Barrier(parties, timeout=10)
        seen: List[int] = []

        def sender(index: int):
            def call() -> Dict[str, Any]:
                # Returns only when all four requests are in flight: a sequential wave times out.
                inner.wait()
                seen.append(index)
                time.sleep(0.02)
                return reply()

            return call

        result = concurrency.send_wave([sender(i) for i in range(parties)])
        self.assertEqual(result.answered, parties)
        self.assertEqual(sorted(seen), list(range(parties)))
        offsets = [outcome.started_at - result.started_at for outcome in result.outcomes]
        self.assertTrue(all(offset >= 0.0 for offset in offsets), offsets)
        self.assertLess(max(offsets), 0.5, "a request of the wave started long after it opened")
        self.assertGreaterEqual(result.wall_s, 0.0)

    def test_outcomes_are_in_request_order(self) -> None:
        result = concurrency.send_wave([lambda: reply() for _ in range(3)])
        self.assertEqual([outcome.index for outcome in result.outcomes], [0, 1, 2])

    def test_a_failed_request_is_kept_as_its_error(self) -> None:
        def boom() -> Dict[str, Any]:
            raise ChatError("HTTP 500 from chat endpoint: boom")

        result = concurrency.send_wave([lambda: reply(), boom])
        self.assertEqual(result.answered, 1)
        self.assertEqual(result.outcomes[1].error, "HTTP 500 from chat endpoint: boom")
        self.assertIsNone(result.outcomes[1].reply)

    def test_a_wave_needs_a_request(self) -> None:
        with self.assertRaises(ValueError):
            concurrency.send_wave([])


class ManyUsersValidityTest(unittest.TestCase):
    def test_a_full_wave_of_cold_requests_is_valid(self) -> None:
        block = assess_many_users_validity(
            status="completed", cached_tokens=0, helper_on=False, helper_state=None,
            wave_users=4, wave_answered=4,
        )
        self.assertTrue(block["valid"])
        self.assertTrue(block["wave_answered"])
        self.assertTrue(block["cached_tokens_zero"])

    def test_one_short_wave_fails_every_row_of_it(self) -> None:
        block = assess_many_users_validity(
            status="completed", cached_tokens=0, helper_on=False, helper_state=None,
            wave_users=4, wave_answered=3,
        )
        self.assertFalse(block["valid"])
        self.assertFalse(block["wave_answered"])

    def test_cached_tokens_fail_the_row(self) -> None:
        block = assess_many_users_validity(
            status="completed", cached_tokens=12, helper_on=False, helper_state=None,
            wave_users=1, wave_answered=1,
        )
        self.assertFalse(block["cached_tokens_zero"])
        self.assertFalse(block["valid"])

    def test_a_helper_row_needs_ready_at_the_wave_start(self) -> None:
        not_ready = assess_many_users_validity(
            status="completed", cached_tokens=0, helper_on=True, helper_state="starting",
            wave_users=1, wave_answered=1,
        )
        self.assertFalse(not_ready["helper_ready_at_wave_start"])
        self.assertFalse(not_ready["valid"])
        ready = assess_many_users_validity(
            status="completed", cached_tokens=0, helper_on=True, helper_state="ready",
            wave_users=1, wave_answered=1, helper_served=True,
        )
        self.assertTrue(ready["valid"])

    def test_the_helper_served_proof_only_fails_when_false(self) -> None:
        unknown = assess_many_users_validity(
            status="completed", cached_tokens=0, helper_on=True, helper_state="ready",
            wave_users=1, wave_answered=1, helper_served=None,
        )
        self.assertTrue(unknown["valid"])
        missed = assess_many_users_validity(
            status="completed", cached_tokens=0, helper_on=True, helper_state="ready",
            wave_users=1, wave_answered=1, helper_served=False,
        )
        self.assertFalse(missed["valid"])


class QualityRowShapeTest(unittest.TestCase):
    """The move of the shared part must leave a quality row exactly as it was."""

    def test_quality_row_fields_are_unchanged(self) -> None:
        matrix = quality.load_quality_matrix(str(REPO / "matrices" / "quality.json"))
        variant = quality.load_variants(matrix, ["spark"])[0]
        unit = quality.QualityUnit(
            variant=variant, task="passkey", sample_id="passkey-4096-0", max_tokens=8,
            messages=[{"role": "user", "content": "a prompt"}], expected="4829157",
            target_tokens=4096, prompt_chars=8,
        )
        context = chatrows.ChatRunContext(
            machine="m", matrix_path="matrices/quality.json", model="model",
            fields=["prefill_helper_node_id"], out_path=Path("out.jsonl"), total_units=1,
        )
        row = quality.build_row(
            context, variant, unit, {"prefill_helper_node_id": "node"}, {"prefill_helper_node_id": ""},
            HelperStatus.from_response(helper_answer()),
        )
        self.assertEqual(
            sorted(row),
            sorted(
                [
                    "timestamp", "machine", "matrix", "model", "variant", "helper_on",
                    "helper_state", "helper_wait_s", "ane_on", "task", "sample_id", "max_tokens",
                    "target_tokens", "prompt_chars", "approximate_prompt_tokens",
                    "desired_settings", "settings_before", "expected",
                ]
            ),
        )

    def test_both_runners_use_the_one_row_base(self) -> None:
        self.assertIs(concurrency.row_base, chatrows.row_base)
        self.assertIs(quality.append_row, chatrows.append_row)
        self.assertIs(quality.ConsecutiveFailureGuard, chatrows.ConsecutiveFailureGuard)


class RunnerTest(unittest.TestCase):
    """Drives concurrency.run() with fake admin and chat clients; no network."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "out.jsonl"
        settings = self.dir / "settings.json"
        settings.write_text(json.dumps({"auth": {"api_key": "test-key"}}), encoding="utf-8")
        self.settings = str(settings)
        self.matrix = self.dir / "matrix.json"
        self.matrix.write_text(
            json.dumps(
                {
                    "model": "test-model",
                    "base_settings": {"prefill_helper_layers": None, "turboquant_kv_enabled": False},
                    "variants": [
                        {"name": "gpu", "helper": "off", "ane": "off", "settings": {}},
                        {"name": "spark", "helper": "on", "ane": "off", "settings": {}},
                    ],
                    "prompt_sizes": [64],
                    "users": [2],
                    "waves": 1,
                    "max_tokens": 8,
                    "temperature": 0,
                }
            ),
            encoding="utf-8",
        )

    def _run(
        self,
        admin: _FakeAdmin,
        chat: _FakeChat,
        *extra: str,
        out: Optional[Path] = None,
    ) -> int:
        argv = [
            "--matrix", str(self.matrix),
            "--base-url", "http://example:8004",
            "--settings", self.settings,
            "--out", str(out or self.out),
            "--machine", "test",
            *extra,
        ]
        with patch("bench.concurrency.OMLXClient", lambda *a, **kw: admin), patch(
            "bench.concurrency.ChatClient", lambda *a, **kw: chat
        ):
            return concurrency.main(argv)

    def _rows(self) -> List[Dict[str, Any]]:
        if not self.out.exists():
            return []
        return [json.loads(line) for line in self.out.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_one_row_per_request_with_the_wave_fields(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(parties=2)
        self.assertEqual(self._run(admin, chat, "--helper-stable-s", "0"), 0)
        rows = self._rows()
        self.assertEqual(len(rows), 4, "two settings x two users of one wave")
        for row in rows:
            self.assertEqual(row["users"], 2)
            self.assertEqual(row["wave"], 0)
            self.assertEqual(row["task"], "many_users")
            self.assertGreaterEqual(row["wave_wall_s"], 0.0)
            self.assertGreaterEqual(row["request_start_offset_s"], 0.0)
            self.assertLess(row["request_start_offset_s"], 0.5)
            self.assertEqual(row["max_tokens"], 8)
            self.assertEqual(row["target_tokens"], 64)
            self.assertTrue(row["validity"]["valid"], row["validity"])
            self.assertEqual(row["usage"]["cached_tokens"], 0)
            self.assertTrue(row["correct"])
        by_wave: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            by_wave.setdefault(row["wave_id"], []).append(row)
        self.assertEqual(sorted(by_wave), ["gpu-64-u2-w0", "spark-64-u2-w0"])
        for wave_rows in by_wave.values():
            self.assertEqual(sorted(row["user_index"] for row in wave_rows), [0, 1])
        spark = [row for row in rows if row["variant"] == "spark"]
        self.assertEqual({row["helper_state"] for row in spark}, {"ready"})
        self.assertEqual({row["helper_layers"] for row in spark}, {49})
        gpu = [row for row in rows if row["variant"] == "gpu"]
        self.assertEqual({row["helper_state"] for row in gpu}, {None})

    def test_settings_are_applied_per_setting_and_restored(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(parties=2)
        self.assertEqual(self._run(admin, chat, "--helper-stable-s", "0", "--helper-node", "node-1"), 0)
        self.assertEqual([applied["prefill_helper_node_id"] for applied in admin.applied], ["", "node-1"])
        self.assertTrue(admin.restored)

    def test_a_failed_request_keeps_its_row_and_fails_the_wave(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(parties=2, failures=1)
        self.assertEqual(self._run(admin, chat, "--helper-stable-s", "0"), 0)
        rows = self._rows()
        self.assertEqual(len(rows), 4)
        failed = [row for row in rows if row["status"] == "error"]
        self.assertEqual(len(failed), 1)
        self.assertIn("409", failed[0]["error"])
        broken = [row for row in rows if row["wave_id"] == failed[0]["wave_id"]]
        self.assertEqual(len(broken), 2, "a wave keeps a row for every request, answered or not")
        for row in broken:
            self.assertFalse(row["validity"]["wave_answered"])
            self.assertFalse(row["validity"]["valid"])
        other = [row for row in rows if row["wave_id"] != failed[0]["wave_id"]]
        self.assertTrue(all(row["validity"]["valid"] for row in other))
        self.assertTrue(admin.restored)

    def test_a_helper_that_is_not_ready_is_flagged(self) -> None:
        admin = _FakeAdmin([helper_answer("starting")])
        chat = _FakeChat(parties=2)
        self.assertEqual(self._run(admin, chat, "--no-helper-wait"), 0)
        spark = [row for row in self._rows() if row["variant"] == "spark"]
        self.assertEqual(len(spark), 2)
        for row in spark:
            self.assertEqual(row["helper_state"], "starting")
            self.assertFalse(row["validity"]["helper_ready_at_wave_start"])
            self.assertFalse(row["validity"]["valid"])

    def test_a_cached_token_fails_the_row(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(parties=2, cached=140)
        self.assertEqual(self._run(admin, chat, "--helper-stable-s", "0"), 0)
        for row in self._rows():
            self.assertFalse(row["validity"]["cached_tokens_zero"])
            self.assertFalse(row["validity"]["valid"])

    def test_the_output_folder_is_made(self) -> None:
        out = self.dir / "new" / "deeper" / "run.jsonl"
        admin, chat = _FakeAdmin(), _FakeChat(parties=2)
        self.assertEqual(self._run(admin, chat, "--helper-stable-s", "0", out=out), 0)
        self.assertTrue(out.is_file())
        self.assertEqual(len(out.read_text(encoding="utf-8").strip().splitlines()), 4)

    def test_an_unwritable_output_stops_before_any_request(self) -> None:
        blocker = self.dir / "blocker"
        blocker.write_text("not a folder", encoding="utf-8")
        admin, chat = _FakeAdmin(), _FakeChat(parties=2)
        with patch("bench.concurrency.OMLXClient", lambda *a, **kw: admin), patch(
            "bench.concurrency.ChatClient", lambda *a, **kw: chat
        ):
            code = concurrency.main(
                [
                    "--matrix", str(self.matrix),
                    "--base-url", "http://example:8004",
                    "--settings", self.settings,
                    "--out", str(blocker / "run.jsonl"),
                    "--machine", "test",
                ]
            )
        self.assertEqual(code, 2)
        self.assertEqual(chat.messages, [])
        self.assertEqual(admin.applied, [])
        self.assertFalse(admin.restored)

    def test_settings_are_restored_when_the_model_never_answers(self) -> None:
        admin = _FakeAdmin()
        chat = _FakeChat(parties=2, ready_error="model 'test-model' did not answer a probe within 600s")
        self.assertNotEqual(self._run(admin, chat), 0)
        self.assertEqual(self._rows(), [])
        self.assertTrue(admin.restored)

    def test_identical_failures_stop_the_run_after_the_wave(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(parties=2, failures=99)
        self.assertNotEqual(self._run(admin, chat, "--helper-stable-s", "0", "--max-consecutive-failures", "2"), 0)
        rows = self._rows()
        self.assertEqual(len(rows), 2, "the whole first wave is kept, then the run stops")
        self.assertTrue(all(row["status"] == "error" for row in rows))
        self.assertTrue(admin.restored)

    def test_dry_run_prints_the_waves_and_sends_nothing(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(parties=2)
        self.assertEqual(self._run(admin, chat, "--dry-run"), 0)
        self.assertEqual(self._rows(), [])
        self.assertEqual(chat.messages, [])
        self.assertFalse(admin.applied)


if __name__ == "__main__":
    unittest.main()
