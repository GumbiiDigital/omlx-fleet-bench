import json
import tempfile
import unittest
from pathlib import Path

from bench import quality
from bench.chat import _normalize

REPO = Path(__file__).resolve().parents[1]
MATRIX = str(REPO / "matrices" / "quality.json")


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


def quality_report_summary(rows):
    from bench.quality_report import write_summary

    return write_summary(rows)


if __name__ == "__main__":
    unittest.main()
