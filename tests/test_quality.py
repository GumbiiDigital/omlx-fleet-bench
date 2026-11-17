import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from bench import quality
from bench.chat import ChatError, _normalize

REPO = Path(__file__).resolve().parents[1]
MATRIX = str(REPO / "matrices" / "quality.json")
BUSY_ERROR = "HTTP 409 from chat endpoint: {\"detail\":\"busy; unload pending\"}"


class MatrixTest(unittest.TestCase):
    def setUp(self):
        self.matrix = quality.load_quality_matrix(MATRIX)

    def test_variants_and_flags(self):
        variants = {v.name: v for v in quality.load_variants(self.matrix)}
        self.assertEqual(set(variants), {"gpu", "ane", "affine4", "affine8", "spark"})
        self.assertTrue(variants["spark"].helper_on)
        self.assertFalse(variants["spark"].ane_on)
        self.assertTrue(variants["ane"].ane_on)
        self.assertTrue(variants["affine4"].settings_patch["turboquant_kv_enabled"])

    def test_only_filter(self):
        variants = quality.load_variants(self.matrix, ["gpu", "spark"])
        self.assertEqual([v.name for v in variants], ["gpu", "spark"])

    def test_merge_settings_sets_node_and_ane(self):
        variant = quality.load_variants(self.matrix, ["spark"])[0]
        merged = variant.merge_settings(self.matrix["base_settings"], "node-1")
        self.assertEqual(merged["prefill_helper_node_id"], "node-1")
        self.assertFalse(merged["qwen35_ane_prefill_enabled"])
        off = quality.load_variants(self.matrix, ["gpu"])[0]
        self.assertEqual(off.merge_settings(self.matrix["base_settings"], "node-1")["prefill_helper_node_id"], "")

    def test_settings_fields_touched_covers_matrix(self):
        from bench.matrix import settings_fields_touched

        fields = settings_fields_touched([], self.matrix["base_settings"])
        self.assertIn("prefill_helper_node_id", fields)
        self.assertIn("turboquant_kv_enabled", fields)


class UnitExpansionTest(unittest.TestCase):
    def setUp(self):
        self.matrix = quality.load_quality_matrix(MATRIX)

    def test_variant_major_order_with_limit(self):
        variants = quality.load_variants(self.matrix)
        units = quality.build_units(self.matrix, variants, only_tasks=["gsm8k"], limit=2)
        self.assertEqual(len(units), 2 * len(variants))
        self.assertEqual([u.variant.name for u in units[:4]], ["gpu", "gpu", "ane", "ane"])

    def test_mmlu_expected_is_index(self):
        variants = quality.load_variants(self.matrix, ["gpu"])
        units = quality.build_units(self.matrix, variants, only_tasks=["mmlu"], limit=1)
        self.assertEqual(len(units), 1)
        self.assertIsInstance(units[0].expected, int)
        self.assertIn("A. ", units[0].messages[-1]["content"])

    def test_passkey_units_carry_target(self):
        variants = quality.load_variants(self.matrix, ["gpu"])
        units = quality.build_units(self.matrix, variants, only_tasks=["passkey"])
        self.assertEqual(len(units), 6)
        self.assertEqual({u.target_tokens for u in units}, {32768, 65536, 131072})
        for unit in units:
            self.assertIn(str(unit.expected), unit.messages[-1]["content"])

    def test_unknown_task_rejected(self):
        matrix = dict(self.matrix)
        matrix["tasks"] = [{"name": "nope"}]
        with self.assertRaises(ValueError):
            quality.build_units(matrix, quality.load_variants(matrix, ["gpu"]))


class CappedRetryTest(unittest.TestCase):
    """Picking the token-capped answers so they can be re-asked with a bigger cap."""

    def setUp(self):
        self.matrix = quality.load_quality_matrix(MATRIX)

    def test_capped_keys_keeps_only_length_rows(self):
        rows = [
            {"variant": "gpu", "task": "mmlu", "sample_id": "m1", "finish_reason": "length"},
            {"variant": "gpu", "task": "mmlu", "sample_id": "m2", "finish_reason": "stop"},
            {"variant": "ane", "task": "gsm8k", "sample_id": "g1", "finish_reason": "length"},
            {"variant": "ane", "task": "gsm8k", "sample_id": "g2", "status": "error"},
        ]
        self.assertEqual(
            quality.capped_keys(rows),
            {("gpu", "mmlu", "m1"), ("ane", "gsm8k", "g1")},
        )

    def test_select_units_keeps_order_and_drops_the_rest(self):
        variants = quality.load_variants(self.matrix, ["gpu", "ane"])
        units = quality.build_units(self.matrix, variants, only_tasks=["gsm8k"], limit=3)
        wanted = {(units[0].variant.name, units[0].task, units[0].sample_id),
                  (units[-1].variant.name, units[-1].task, units[-1].sample_id)}
        picked = quality.select_units(units, wanted)
        self.assertEqual([u.sample_id for u in picked], [units[0].sample_id, units[-1].sample_id])
        self.assertEqual([u.variant.name for u in picked], [units[0].variant.name, units[-1].variant.name])

    def test_scale_max_tokens_multiplies_and_keeps_order(self):
        variants = quality.load_variants(self.matrix, ["gpu"])
        units = quality.build_units(self.matrix, variants, only_tasks=["gsm8k"], limit=2)
        scaled = quality.scale_max_tokens(units, 8)
        self.assertEqual([u.max_tokens for u in scaled], [u.max_tokens * 8 for u in units])
        self.assertEqual([u.sample_id for u in scaled], [u.sample_id for u in units])

    def test_scale_by_one_changes_nothing(self):
        variants = quality.load_variants(self.matrix, ["gpu"])
        units = quality.build_units(self.matrix, variants, only_tasks=["mmlu"], limit=2)
        self.assertEqual([u.max_tokens for u in quality.scale_max_tokens(units, 1)],
                         [u.max_tokens for u in units])

    def test_scale_below_one_rejected(self):
        with self.assertRaises(ValueError):
            quality.scale_max_tokens([], 0)


class PasskeyCacheBustTest(unittest.TestCase):
    """Same prompt text for every variant let oMLX serve later variants from its prompt
    cache, so the long read was never fresh. Each unit now carries its own tag line."""

    def setUp(self):
        self.matrix = quality.load_quality_matrix(MATRIX)

    def _units(self, matrix, names=("gpu", "affine4")):
        variants = quality.load_variants(matrix, list(names))
        return quality.build_units(matrix, variants, only_tasks=["passkey"])

    def test_one_tag_per_variant_and_sample(self):
        units = self._units(self.matrix)
        self.assertEqual(len(units), 2 * 6)
        firsts = [u.messages[-1]["content"].split("\n", 1)[0] for u in units]
        for tag in firsts:
            self.assertTrue(tag.startswith("Request tag: "), tag)
        self.assertEqual(len(set(firsts)), len(firsts), "every passkey prompt needs its own first line")

    def test_needle_and_question_unchanged(self):
        from bench.qa import PASSKEY_QUESTION

        units = self._units(self.matrix)
        for unit in units:
            content = unit.messages[-1]["content"]
            self.assertIn(str(unit.expected), content)
            self.assertTrue(content.endswith(PASSKEY_QUESTION))

    def test_old_behaviour_without_cache_bust(self):
        matrix = dict(self.matrix)
        matrix["tasks"] = [dict(t, cache_bust=False) for t in self.matrix["tasks"]]
        units = self._units(matrix)
        contents = {u.messages[-1]["content"] for u in units}
        self.assertEqual(len(contents), 6, "cache_bust false must keep prompts byte-identical across variants")


class ScoringDispatchTest(unittest.TestCase):
    def test_dispatch(self):
        variant = quality.load_variants(quality.load_quality_matrix(MATRIX), ["gpu"])[0]
        unit = quality.QualityUnit(
            variant=variant, task="gsm8k", sample_id="x", max_tokens=8,
            messages=[], expected="steps #### 18",
        )
        self.assertTrue(quality.score_unit(unit, "#### 18")["correct"])
        mmlu = quality.QualityUnit(
            variant=variant, task="mmlu", sample_id="y", max_tokens=8, messages=[], expected=2,
        )
        self.assertTrue(quality.score_unit(mmlu, "Answer: C")["correct"])


class ChatNormalizeTest(unittest.TestCase):
    def test_reasoning_only_reply(self):
        payload = {
            "choices": [{"message": {"reasoning_content": "thinking"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 59, "completion_tokens": 8,
                      "prompt_tokens_details": {"cached_tokens": 54},
                      "time_to_first_token": 0.17},
        }
        out = _normalize(payload, 0.3)
        self.assertEqual(out["content"], "")
        self.assertEqual(out["reasoning"], "thinking")
        self.assertEqual(out["usage"]["cached_tokens"], 54)
        self.assertEqual(out["server_timing"]["time_to_first_token"], 0.17)

    def test_missing_choices_raises(self):
        with self.assertRaises(Exception):
            _normalize({}, 0.1)


class SummaryTest(unittest.TestCase):
    def test_accuracy_table(self):
        rows = [
            {"variant": "gpu", "task": "gsm8k", "correct": True, "content": "#### 18", "status": "completed"},
            {"variant": "gpu", "task": "gsm8k", "correct": False, "content": "#### 17", "status": "completed"},
            {"variant": "gpu", "task": "passkey", "correct": True, "content": "4829157",
             "status": "completed", "target_tokens": 32768,
             "usage": {"prompt_tokens": 33000}},
        ]
        text = quality_report_summary(rows)
        self.assertIn("| gpu | gsm8k | 1 | 2 | 50.0% |", text)
        self.assertIn("101%", text)

    def test_empty_rows(self):
        self.assertIn("Rows: 0", quality_report_summary([]))

    def test_capped_column_counts_length_rows(self):
        rows = [
            {"variant": "gpu", "task": "mmlu", "correct": False, "status": "completed",
             "finish_reason": "length", "content": ""},
            {"variant": "gpu", "task": "mmlu", "correct": True, "status": "completed",
             "finish_reason": "stop", "content": "Answer: B"},
            {"variant": "gpu", "task": "mmlu", "correct": True, "status": "completed",
             "finish_reason": "length", "content": "Answer: C"},
        ]
        text = quality_report_summary(rows)
        self.assertIn("| Capped |", text)
        self.assertIn("| gpu | mmlu | 2 | 3 | 66.7% | 0 | - | 2 |", text)


class ReplacementTest(unittest.TestCase):
    """Re-asked answers stand in for the capped ones they replace."""

    def test_apply_replacements_swaps_matching_rows(self):
        from bench.quality_report import apply_replacements

        base = [
            {"variant": "gpu", "task": "mmlu", "sample_id": "m1", "correct": False,
             "finish_reason": "length"},
            {"variant": "gpu", "task": "mmlu", "sample_id": "m2", "correct": True,
             "finish_reason": "stop"},
        ]
        new = [{"variant": "gpu", "task": "mmlu", "sample_id": "m1", "correct": True,
                "finish_reason": "stop"}]
        out = apply_replacements(base, new)
        self.assertEqual(len(out), 2)
        self.assertEqual([row["sample_id"] for row in out], ["m1", "m2"])
        self.assertTrue(out[0]["correct"])
        self.assertFalse(base[0]["correct"])

    def test_apply_replacements_rejects_unknown_key(self):
        from bench.quality_report import apply_replacements

        base = [{"variant": "gpu", "task": "mmlu", "sample_id": "m1", "correct": False}]
        new = [{"variant": "gpu", "task": "mmlu", "sample_id": "nope", "correct": True}]
        with self.assertRaises(ValueError):
            apply_replacements(base, new)

    def test_apply_replacements_with_no_new_rows_keeps_base(self):
        from bench.quality_report import apply_replacements

        base = [{"variant": "gpu", "task": "mmlu", "sample_id": "m1", "correct": False}]
        self.assertEqual(apply_replacements(base, []), base)


class ConsecutiveFailureGuardTest(unittest.TestCase):
    def test_stops_at_limit_of_identical_errors(self) -> None:
        guard = quality.ConsecutiveFailureGuard(3)
        self.assertFalse(guard.record_failure(BUSY_ERROR))
        self.assertFalse(guard.record_failure(BUSY_ERROR))
        self.assertEqual(guard.count, 2)
        self.assertTrue(guard.record_failure(BUSY_ERROR))

    def test_different_error_restarts_the_count(self) -> None:
        guard = quality.ConsecutiveFailureGuard(2)
        self.assertFalse(guard.record_failure(BUSY_ERROR))
        self.assertFalse(guard.record_failure("HTTP 500 from chat endpoint: boom"))
        self.assertEqual(guard.count, 1)

    def test_success_clears_the_count(self) -> None:
        guard = quality.ConsecutiveFailureGuard(2)
        guard.record_failure(BUSY_ERROR)
        guard.record_success()
        self.assertEqual(guard.count, 0)
        self.assertFalse(guard.record_failure(BUSY_ERROR))

    def test_limit_below_one_rejected(self) -> None:
        with self.assertRaises(ValueError):
            quality.ConsecutiveFailureGuard(0)


class _FakeAdmin:
    """Records settings writes and whether the restore block ran."""

    def __init__(self) -> None:
        self.applied: List[Dict[str, Any]] = []
        self.restored = False

    def login(self) -> None:
        return None

    @contextmanager
    def preserved_settings(self, model: str, fields: List[str]) -> Any:
        try:
            yield {field: None for field in fields}
        finally:
            self.restored = True

    def apply_settings(self, model: str, desired: Dict[str, Any], fields: List[str]) -> None:
        self.applied.append({field: desired.get(field) for field in fields})


class _FakeChat:
    """Stands in for ChatClient; logs the order of probe and chat calls."""

    def __init__(
        self,
        *,
        error: str = "",
        ready_error: str = "",
        errors: Optional[List[str]] = None,
        content: str = "#### 18",
    ) -> None:
        self.error = error
        self.ready_error = ready_error
        self.errors = list(errors or [])
        self.content = content
        self.events: List[Any] = []

    def wait_until_ready(
        self, model: str, *, timeout_s: float = 600.0, interval_s: float = 5.0
    ) -> Dict[str, Any]:
        self.events.append(("wait", model, timeout_s))
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
        self.events.append(("chat", model))
        if self.errors:
            raise ChatError(self.errors.pop(0))
        if self.error:
            raise ChatError(self.error)
        return {
            "content": self.content,
            "reasoning": "",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cached_tokens": None},
            "server_timing": {},
            "latency_s": 0.1,
        }


class RunnerTest(unittest.TestCase):
    """Drives quality.run() with fake admin and chat clients."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "out.jsonl"
        settings = self.dir / "settings.json"
        settings.write_text(json.dumps({"auth": {"api_key": "test-key"}}), encoding="utf-8")
        self.settings = str(settings)

    def _run(
        self,
        admin: _FakeAdmin,
        chat: _FakeChat,
        *extra: str,
        limit: int = 1,
    ) -> int:
        argv = [
            "--matrix", MATRIX,
            "--base-url", "http://example:8004",
            "--settings", self.settings,
            "--out", str(self.out),
            "--machine", "test",
            "--only-variants", "gpu,ane",
            "--only-tasks", "gsm8k",
            "--limit", str(limit),
            *extra,
        ]
        with patch("bench.quality.OMLXClient", lambda *a, **kw: admin), patch(
            "bench.quality.ChatClient", lambda *a, **kw: chat
        ):
            return quality.main(argv)

    def _rows(self) -> List[Dict[str, Any]]:
        return quality.read_jsonl(self.out) if self.out.exists() else []

    def test_waits_for_model_before_each_block(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat()
        self.assertEqual(self._run(admin, chat), 0)
        self.assertEqual(
            chat.events,
            [("wait", "Qwen3.8-27B-oQ4e-mtp", 600.0), ("chat", "Qwen3.8-27B-oQ4e-mtp"),
             ("wait", "Qwen3.8-27B-oQ4e-mtp", 600.0), ("chat", "Qwen3.8-27B-oQ4e-mtp")],
        )
        self.assertEqual([row["status"] for row in self._rows()], ["completed", "completed"])
        self.assertEqual([row["variant"] for row in self._rows()], ["gpu", "ane"])

    def test_ready_timeout_stops_before_any_row(self) -> None:
        admin = _FakeAdmin()
        chat = _FakeChat(ready_error="model 'Qwen3.8-27B-oQ4e-mtp' did not answer a probe within 600s")
        self.assertNotEqual(self._run(admin, chat), 0)
        self.assertEqual(self._rows(), [])
        self.assertTrue(admin.restored)

    def test_identical_failures_stop_the_run_and_restore_settings(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(error=BUSY_ERROR)
        self.assertNotEqual(self._run(admin, chat, "--max-consecutive-failures", "1"), 0)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "error")
        self.assertIn("409", rows[0]["error"])
        self.assertEqual([event[0] for event in chat.events], ["wait", "chat"])
        self.assertTrue(admin.restored)

    def test_default_limit_is_five_identical_failures(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat(error=BUSY_ERROR)
        self.assertNotEqual(self._run(admin, chat, limit=5), 0)
        self.assertEqual(len(self._rows()), 5)
        self.assertTrue(admin.restored)

    def test_different_errors_do_not_stop_the_run(self) -> None:
        admin = _FakeAdmin()
        chat = _FakeChat(errors=[BUSY_ERROR, "HTTP 500 from chat endpoint: boom"])
        self.assertEqual(self._run(admin, chat, "--max-consecutive-failures", "2"), 0)
        self.assertEqual([row["status"] for row in self._rows()], ["error", "error"])
        self.assertTrue(admin.restored)

    def test_rows_record_the_cap_used(self) -> None:
        admin, chat = _FakeAdmin(), _FakeChat()
        self.assertEqual(self._run(admin, chat, limit=1), 0)
        self.assertEqual([row["max_tokens"] for row in self._rows()], [2048, 2048])

    def test_retry_capped_and_scale_narrow_the_run(self) -> None:
        capped = self.dir / "capped.jsonl"
        capped.write_text(
            json.dumps(
                {"variant": "ane", "task": "gsm8k", "sample_id": "gsm8k-0000", "finish_reason": "length"}
            ) + "\n",
            encoding="utf-8",
        )
        admin, chat = _FakeAdmin(), _FakeChat()
        code = self._run(
            admin, chat,
            "--retry-capped", str(capped),
            "--max-tokens-scale", "8",
            limit=2,
        )
        self.assertEqual(code, 0)
        rows = self._rows()
        self.assertEqual([(row["variant"], row["sample_id"]) for row in rows], [("ane", "gsm8k-0000")])
        self.assertEqual(rows[0]["max_tokens"], 16384)
        self.assertEqual([event[0] for event in chat.events], ["wait", "wait", "chat"])


def quality_report_summary(rows):
    from bench.quality_report import write_summary

    return write_summary(rows)


if __name__ == "__main__":
    unittest.main()
