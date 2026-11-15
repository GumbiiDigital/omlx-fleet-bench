"""Tests for report aggregation and exit codes."""

import json
import tempfile
import unittest
from pathlib import Path

from bench.report import group_rows, report_all


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


if __name__ == "__main__":
    unittest.main()