"""Tests for report aggregation and exit codes."""

import json
import tempfile
import unittest
from pathlib import Path

from bench.report import group_rows, memory_panels, report_all, summary_markdown, ttft_lines, ttft_panels


def _row(
    machine: str,
    variant: str,
    size: int,
    repeat: int,
    tps: float,
    ttft: float,
    valid: bool,
) -> dict:
    return {
        "machine": machine,
        "model": "Qwen3.8-27B-oQ4e-mtp",
        "variant": variant,
        "prompt_size": size,
        "repeat_index": repeat,
        "runs_per_cell": 3,
        "metrics": {"processing_tps": tps, "ttft_ms": ttft},
        "validity": {"valid": valid},
    }


class TestReport(unittest.TestCase):
    def test_group_stats(self) -> None:
        rows = [
            _row("m1", "gpu", 32768, 0, 300.0, 100000.0, True),
            _row("m1", "gpu", 32768, 1, 301.0, 100100.0, True),
            _row("m1", "gpu", 32768, 2, 302.0, 100200.0, True),
        ]
        grouped = group_rows(rows)
        key = ("m1", "Qwen3.8-27B-oQ4e-mtp", "gpu", 32768)
        self.assertEqual(grouped[key].n_valid, 3)
        self.assertFalse(grouped[key].incomplete)
        self.assertFalse(grouped[key].noisy)

    def test_noisy_detection(self) -> None:
        rows = [
            _row("m1", "ane", 32768, 0, 300.0, 90000.0, True),
            _row("m1", "ane", 32768, 1, 400.0, 95000.0, True),
            _row("m1", "ane", 32768, 2, 310.0, 91000.0, True),
        ]
        grouped = group_rows(rows)
        cell = grouped[("m1", "Qwen3.8-27B-oQ4e-mtp", "ane", 32768)]
        self.assertTrue(cell.noisy)

    def test_report_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "results" / "test"
            report_dir = Path(tmp) / "report"
            results.mkdir(parents=True)
            good = results / "good.jsonl"
            with open(good, "w", encoding="utf-8") as fh:
                for i in range(3):
                    fh.write(json.dumps(_row("m1", "gpu", 8192, i, 300.0 + i, 50000.0, True)))
                    fh.write("\n")
            code_ok = report_all(results.parent, report_dir)
            self.assertEqual(code_ok, 0)
            self.assertTrue((report_dir / "summary.md").is_file())

            bad = results / "bad.jsonl"
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(_row("m1", "gpu", 65536, 0, 100.0, 50000.0, True)))
                fh.write("\n")
                fh.write(json.dumps(_row("m1", "gpu", 65536, 1, 200.0, 50000.0, True)))
                fh.write("\n")
            code_bad = report_all(results.parent, report_dir)
            self.assertEqual(code_bad, 1)


class TestPanels(unittest.TestCase):
    def _cells(self):
        rows = []
        for variant, ttft, peak in (("gpu", 100000.0, 20.0), ("spark", 25000.0, 20.0), ("affine4", 100000.0, 15.0)):
            for repeat in range(3):
                row = _row("m1", variant, 32768, repeat, 300.0, ttft, True)
                row["metrics"]["peak_memory_bytes"] = peak * 2**30
                rows.append(row)
        return list(group_rows(rows).values())

    def test_ttft_panel_notes_speedup_against_baseline(self) -> None:
        (panel,) = ttft_panels(self._cells(), "gpu")
        self.assertEqual(panel.title, "32K prompt")
        by_label = {row.label: row for row in panel.rows}
        self.assertEqual(by_label["GPU only"].note, "baseline")
        self.assertEqual(by_label["+ Spark helper"].value_text, "25.0 s")
        self.assertEqual(by_label["+ Spark helper"].note, "4.0× faster")

    def test_memory_panel_notes_change_against_baseline(self) -> None:
        (panel,) = memory_panels(self._cells(), "gpu")
        by_label = {row.label: row for row in panel.rows}
        self.assertEqual(by_label["Affine4 KV"].value_text, "15.0 GB")
        self.assertEqual(by_label["Affine4 KV"].note, "−25.0%")

    def test_rows_without_a_prompt_size_are_not_speed_rows(self) -> None:
        rows = [_row("m1", "gpu", 8192, i, 300.0, 50000.0, True) for i in range(3)]
        rows.append({"machine": "m1", "variant": "gpu", "task": "mmlu", "correct": True})
        self.assertEqual(len(group_rows(rows)), 1)

    def test_summary_lists_peak_memory_and_flags(self) -> None:
        text = summary_markdown(self._cells())
        self.assertIn("| m1 | Qwen3.8-27B-oQ4e-mtp | affine4 | 32768 | 3/3 |", text)
        self.assertIn("| 15.0 | - |", text)

    def test_report_writes_light_and_dark_charts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "speed.jsonl"
            with open(results, "w", encoding="utf-8") as fh:
                for i in range(3):
                    fh.write(json.dumps(_row("m1", "gpu", 8192, i, 300.0 + i, 50000.0, True)) + "\n")
            self.assertEqual(report_all(results, Path(tmp) / "report"), 0)
            charts = sorted(p.name for p in (Path(tmp) / "report" / "charts").iterdir())
            self.assertEqual(
                charts,
                ["m1__Qwen3.8-27B-oQ4e-mtp-ttft-dark.svg", "m1__Qwen3.8-27B-oQ4e-mtp-ttft-light.svg"],
            )


class TestTtftLines(unittest.TestCase):
    def _cells(self):
        rows = []
        for variant, base in (("gpu", 1.7), ("spark", 1.5)):
            for size, factor in ((1024, 1.0), (8192, 5.0), (131072, 80.0)):
                for repeat in range(2):
                    rows.append(_row("m1", variant, size, repeat, 900.0, base * factor * 1000.0, True))
        return list(group_rows(rows).values())

    def test_one_line_per_variant_in_the_fixed_order(self) -> None:
        panel = ttft_lines(self._cells())
        self.assertEqual([line.label for line in panel.series], ["GPU only", "+ Spark helper"])

    def test_points_carry_the_size_and_the_wait(self) -> None:
        panel = ttft_lines(self._cells())
        point = panel.series[0].points[-1]
        self.assertEqual((point.x, point.x_text, point.y_text), (131072, "128K", "136 s"))

    def test_axes_cover_every_point_with_ticks_inside(self) -> None:
        panel = ttft_lines(self._cells())
        self.assertEqual((panel.x_min, panel.x_max), (1024, 131072))
        self.assertAlmostEqual(panel.y_min, 1.5)
        self.assertAlmostEqual(panel.y_max, 136.0)
        ys = [value for value, _ in panel.y_ticks]
        self.assertEqual(ys, [2.0, 5.0, 10.0, 20.0, 50.0, 100.0])
        self.assertEqual([label for _, label in panel.x_ticks], ["1K", "8K", "128K"])

    def test_a_cell_without_a_valid_run_is_left_out(self) -> None:
        rows = [
            _row("m1", "gpu", 1024, 0, 900.0, 1700.0, True),
            _row("m1", "gpu", 8192, 0, 900.0, 8700.0, True),
            _row("m1", "spark", 1024, 0, 900.0, 1500.0, False),
            _row("m1", "spark", 8192, 0, 900.0, 6000.0, True),
        ]
        panel = ttft_lines(list(group_rows(rows).values()))
        self.assertEqual([line.label for line in panel.series], ["GPU only", "+ Spark helper"])
        self.assertEqual([p.x for p in panel.series[1].points], [8192])


if __name__ == "__main__":
    unittest.main()