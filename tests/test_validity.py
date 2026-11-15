"""Tests for run validity rules and per-run log windows."""

import tempfile
import unittest
from pathlib import Path

from bench.collect import read_server_log, read_server_log_since
from bench.validity import assess_validity

FIXTURE = Path(__file__).parent / "fixtures" / "server-log-sample.log"


def _check(bench_id: str, *, ane_on: bool, helper_on: bool = False, features=None):
    parsed = read_server_log(str(FIXTURE))[bench_id]
    return assess_validity(
        status="completed",
        end_event_type="upload_skipped",
        feature_keys=features or [],
        helper_on=helper_on,
        ane_on=ane_on,
        log_parsed=parsed,
    )


class TestValidity(unittest.TestCase):
    def test_ane_run_is_valid_from_observed_operations(self) -> None:
        # bench-206d1502ea1a: ANE on, summary accounting=prompt_estimate, mlp operations=1008.
        self.assertTrue(_check("bench-206d1502ea1a", ane_on=True)["valid"])

    def test_ane_off_run_is_valid(self) -> None:
        self.assertTrue(_check("bench-efaaa0ac02ba", ane_on=False)["valid"])

    def test_ane_cell_mismatch_is_invalid(self) -> None:
        result = _check("bench-efaaa0ac02ba", ane_on=True)
        self.assertFalse(result["valid"])
        self.assertFalse(result["ane_tiles_match"])

    def test_helper_flag_required_for_helper_cell(self) -> None:
        self.assertFalse(_check("bench-efaaa0ac02ba", ane_on=False, helper_on=True)["valid"])
        ok = _check("bench-efaaa0ac02ba", ane_on=False, helper_on=True, features=["prefill_accelerator"])
        self.assertTrue(ok["valid"])

    def test_upload_done_is_invalid(self) -> None:
        parsed = read_server_log(str(FIXTURE))["bench-efaaa0ac02ba"]
        result = assess_validity(
            status="completed", end_event_type="upload_done", feature_keys=[],
            helper_on=False, ane_on=False, log_parsed=parsed,
        )
        self.assertFalse(result["valid"])


class TestLogWindow(unittest.TestCase):
    def test_since_offset_skips_older_runs(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        cut = text.index("Benchmark started: bench-59844c19a802")
        cut = text.rfind("\n", 0, cut) + 1
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".log") as fh:
            fh.write(text)
        runs = read_server_log_since(fh.name, len(text[:cut].encode("utf-8")))
        self.assertIn("bench-59844c19a802", runs)
        self.assertNotIn("bench-206d1502ea1a", runs)

    def test_rotated_log_falls_back_to_whole_file(self) -> None:
        runs = read_server_log_since(str(FIXTURE), 10 ** 12)
        self.assertIn("bench-206d1502ea1a", runs)


if __name__ == "__main__":
    unittest.main()
