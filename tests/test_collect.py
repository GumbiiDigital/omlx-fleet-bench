"""Tests for server.log parsing."""

import unittest
from pathlib import Path

from bench.collect import parse_server_log, read_server_log

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "server-log-sample.log"


class TestCollect(unittest.TestCase):
    def test_reads_fixture_file(self) -> None:
        runs = read_server_log(str(FIXTURE))
        self.assertIn("bench-206d1502ea1a", runs)

    def test_bench_206d_ane_and_tps(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        runs = parse_server_log(text)
        row = runs["bench-206d1502ea1a"]
        self.assertTrue(row["ane_enabled"])
        self.assertEqual(row["full_ane_tiles"], 16)
        self.assertAlmostEqual(row["processing_tps"], 376.1)
        self.assertEqual(row["cached_tokens"], 0)

    def test_bench_efaaa_ane_off(self) -> None:
        runs = parse_server_log(FIXTURE.read_text(encoding="utf-8"))
        row = runs["bench-efaaa0ac02ba"]
        self.assertFalse(row["ane_enabled"])
        self.assertEqual(row["full_ane_tiles"], 0)
        self.assertAlmostEqual(row["processing_tps"], 298.4)

    def test_bench_59844_affine_run(self) -> None:
        runs = parse_server_log(FIXTURE.read_text(encoding="utf-8"))
        row = runs["bench-59844c19a802"]
        self.assertFalse(row["ane_enabled"])
        self.assertAlmostEqual(row["processing_tps"], 299.2)

    def test_kv_line_parsing(self) -> None:
        snippet = (
            "2026-11-14 21:00:00,000 - omlx - INFO - [-] - Benchmark started: bench-deadbeef01\n"
            "2026-11-14 21:00:01,000 - omlx - INFO - [-] - affine4: converted 16/64 cache layers to 4.0-bit\n"
            "2026-11-14 21:00:02,000 - omlx - INFO - [-] - [benchmark-pp-result] "
            "pp=100 processing_tps=1.0 gen_tps=1.0 ttft_ms=1.0 e2e_ms=1.0 cached_tokens=0\n"
        )
        runs = parse_server_log(snippet)
        self.assertEqual(len(runs["bench-deadbeef01"]["kv_lines"]), 1)
        self.assertEqual(runs["bench-deadbeef01"]["kv_lines"][0]["scheme"], "affine4")


if __name__ == "__main__":
    unittest.main()