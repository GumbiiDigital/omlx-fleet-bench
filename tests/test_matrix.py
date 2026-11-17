"""Tests for matrix expansion and ordering."""

import unittest
from pathlib import Path

from bench.matrix import expand_runs, load_and_expand, load_matrix

MATRIX = Path(__file__).resolve().parents[1] / "matrices" / "m3-ultra-spark.json"
HELPER_READY = Path(__file__).resolve().parents[1] / "matrices" / "m3-ultra-a-helper-ready.json"
HELPER_LAYERS = Path(__file__).resolve().parents[1] / "matrices" / "m3-ultra-a-helper-layers.json"


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


class TestHelperMatrices(unittest.TestCase):
    def test_helper_ready_matrix_loads(self) -> None:
        specs = load_and_expand(str(HELPER_READY))
        self.assertEqual(len(specs), 6 * 2 * 2)
        self.assertEqual({s.variant for s in specs}, {"gpu", "spark"})
        self.assertEqual({s.prompt_size for s in specs}, {1024, 32768})

    def test_helper_ready_filter_puts_a_helper_run_after_an_off_run(self) -> None:
        specs = load_and_expand(
            str(HELPER_READY), only_cells=["gpu:1024", "spark:32768"]
        )
        self.assertEqual(
            [(s.repeat_index, s.variant, s.prompt_size) for s in specs],
            [
                (repeat, variant, size)
                for repeat in range(6)
                for variant, size in (("gpu", 1024), ("spark", 32768))
            ],
        )
        self.assertFalse(specs[0].helper_on)
        self.assertTrue(specs[1].helper_on)

    def test_helper_layers_matrix_loads(self) -> None:
        matrix = load_matrix(str(HELPER_LAYERS))
        specs = expand_runs(matrix)
        self.assertEqual(len(specs), 3 * 2 * 5)
        self.assertEqual(
            [s.variant for s in specs[:5]],
            ["gpu", "spark-auto", "spark-32", "spark-49", "spark-63"],
        )
        by_name = {s.variant: s for s in specs}
        self.assertFalse(by_name["gpu"].helper_on)
        self.assertTrue(all(by_name[name].helper_on for name in ("spark-auto", "spark-32", "spark-49", "spark-63")))

    def test_helper_layers_pins_reach_the_settings(self) -> None:
        matrix = load_matrix(str(HELPER_LAYERS))
        specs = expand_runs(matrix)
        merged = {
            name: next(s for s in specs if s.variant == name).merge_settings(
                matrix["base_settings"], "NODE123"
            )
            for name in ("gpu", "spark-auto", "spark-32", "spark-49", "spark-63")
        }
        self.assertIsNone(merged["spark-auto"]["prefill_helper_layers"])
        self.assertEqual(merged["spark-32"]["prefill_helper_layers"], 32)
        self.assertEqual(merged["spark-49"]["prefill_helper_layers"], 49)
        self.assertEqual(merged["spark-63"]["prefill_helper_layers"], 63)
        self.assertEqual(merged["gpu"]["prefill_helper_node_id"], "")
        self.assertEqual(merged["spark-49"]["prefill_helper_node_id"], "NODE123")
        for settings in merged.values():
            self.assertFalse(settings["qwen35_ane_prefill_enabled"])
            self.assertFalse(settings["turboquant_kv_enabled"])
            self.assertEqual(settings["turboquant_kv_scheme"], "affine4")


if __name__ == "__main__":
    unittest.main()