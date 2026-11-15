"""Tests for matrix expansion and ordering."""

import unittest
from pathlib import Path

from bench.matrix import expand_runs, load_and_expand, load_matrix

MATRIX = Path(__file__).resolve().parents[1] / "matrices" / "m3-ultra-spark.json"


class TestMatrix(unittest.TestCase):
    def test_m3_ultra_run_count(self) -> None:
        specs = load_and_expand(str(MATRIX))
        self.assertEqual(len(specs), 3 * 4 * 4)

    def test_ab_order_repeat_size_variant(self) -> None:
        specs = load_and_expand(str(MATRIX))
        first_twelve = [((s.repeat_index, s.prompt_size, s.variant)) for s in specs[:12]]
        self.assertEqual(
            first_twelve,
            [
                (0, 8192, "gpu"),
                (0, 8192, "ane"),
                (0, 8192, "spark"),
                (0, 8192, "ane_spark"),
                (0, 32768, "gpu"),
                (0, 32768, "ane"),
                (0, 32768, "spark"),
                (0, 32768, "ane_spark"),
                (0, 65536, "gpu"),
                (0, 65536, "ane"),
                (0, 65536, "spark"),
                (0, 65536, "ane_spark"),
            ],
        )

    def test_helper_node_applied_only_when_on(self) -> None:
        matrix = load_matrix(str(MATRIX))
        specs = expand_runs(matrix)
        gpu = next(s for s in specs if s.variant == "gpu" and s.prompt_size == 8192)
        spark = next(s for s in specs if s.variant == "spark" and s.prompt_size == 8192)
        gsettings = gpu.merge_settings(matrix["base_settings"], "NODE123")
        ssettings = spark.merge_settings(matrix["base_settings"], "NODE123")
        self.assertEqual(gsettings["prefill_helper_node_id"], "")
        self.assertEqual(ssettings["prefill_helper_node_id"], "NODE123")

    def test_refuse_public_align_flag(self) -> None:
        data = load_matrix(str(MATRIX))
        data["align_prompt_to_ane"] = False
        with self.assertRaises(ValueError):
            expand_runs(data)

    def test_only_cells_filter(self) -> None:
        specs = load_and_expand(str(MATRIX), only_cells=["gpu:8192", "ane:8192"])
        self.assertEqual(len(specs), 3 * 2)


if __name__ == "__main__":
    unittest.main()