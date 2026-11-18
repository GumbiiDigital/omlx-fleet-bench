"""Tests for report aggregation and exit codes."""

import json
import tempfile
import unittest
from pathlib import Path

from bench import latency
from bench.report import (
    group_rows,
    memory_panels,
    report_all,
    request_markdown,
    setting_panels,
    summary_markdown,
    ttft_lines,
    ttft_panels,
)


def _request_row(
    ttft: float,
    *,
    size: int = 32768,
    helper: bool = True,
    ask=None,
    took=None,
    state: str = "ready",
    wait: float = 0.0,
    status: str = "completed",
    correct: bool = True,
    cached: int = 0,
    validity=None,
) -> dict:
    row = {
        "machine": "m1",
        "helper_on": helper,
        "helper_state": state if helper else None,
        "helper_wait_s": wait,
        "helper_layers": took,
        "desired_settings": {"prefill_helper_layers": ask},
        "target_tokens": size,
        "status": status,
        "correct": correct,
        "usage": {"cached_tokens": cached},
        "server_timing": {"time_to_first_token": ttft},
    }
    if validity is not None:
        row["validity"] = validity
    return row


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


class TestRequestMarkdown(unittest.TestCase):
    def _requests(self):
        rows = [
            (_request_row(109.70, state="connecting", took=49), "chat", "no wait"),
            (_request_row(29.31, state="ready", wait=20.0, took=49), "chat", "wait"),
            (
                _request_row(30.0, state="starting", took=49, validity={"valid": True, "helper_ready_at_start": True}),
                "speed test",
                "no wait",
            ),
            (_request_row(0.14, helper=False), "chat", "wait"),
        ]
        return [latency.from_row(row, path=path, arm=arm) for row, path, arm in rows]

    def test_one_line_per_request_with_its_helper_state(self):
        text = request_markdown(self._requests(), "Every request")
        self.assertIn("# Every request", text)
        self.assertIn("| chat | no wait | 32K | Automatic | on | connecting | 0.0 | 109.70 | 49 | 0 | yes | no validity marks |", text)
        self.assertIn("| chat | wait | 32K | Automatic | on | ready | 20.0 | 29.31 | 49 | 0 | yes | no validity marks |", text)
        self.assertIn("| speed test | no wait | 32K | Automatic | on | starting | 0.0 | 30.00 | 49 | 0 | yes | - |", text)
        self.assertIn("| chat | wait | 32K | Mac alone | off | none | 0.0 | 0.14 | none | 0 | yes | no validity marks |", text)
        self.assertEqual(text.count("\n| "), 6)  # header, separator and four requests

    def test_a_row_that_records_no_checks_says_so_rather_than_dash(self):
        text = request_markdown([latency.from_row(_request_row(109.70), path="chat", arm="no wait")], "Every request")
        self.assertIn("| no validity marks |", text)
        # The note names the kind of row the study actually holds.
        self.assertIn("These rows carry no validity block", text)
        self.assertNotIn("A speed row carries", text)

    def test_a_mixed_study_explains_both_kinds_of_row(self):
        text = request_markdown(self._requests(), "Every request")
        self.assertIn("A speed row carries a validity block; a chat row carries none", text)

    def test_a_speed_only_study_says_every_row_carries_a_validity_block(self):
        row = _request_row(29.5, validity={"valid": True})
        text = request_markdown([latency.from_row(row, path="speed test", arm="no wait")], "Every request")
        self.assertIn("Every row here carries a validity block", text)

    def test_a_helper_row_that_does_not_record_its_layers_says_so(self):
        row = _request_row(29.5)
        row["prompt_size"] = 32768
        row["metrics"] = {"ttft_ms": 29500.0}
        row["log"] = {"cached_tokens": 0}
        text = request_markdown([latency.from_row(row, path="speed test", arm="no wait")], "Every request")
        self.assertIn("| not recorded |", text)
        self.assertNotIn("| none |", text)

    def test_a_failed_check_is_named_on_its_row(self):
        row = _request_row(30.0, validity={"valid": False, "helper_ready_at_start": False})
        text = request_markdown([latency.from_row(row, path="speed test", arm="no wait")], "Every request")
        self.assertIn("| helper_ready_at_start |", text)


class TestSettingPanels(unittest.TestCase):
    def _groups(self):
        rows = [
            _request_row(109.70, helper=False, size=32768),
            _request_row(109.76, helper=False, size=32768),
            _request_row(32.1, ask=None, took=49, size=32768),
            _request_row(29.8, ask=49, took=49, size=32768),
            _request_row(178.7, ask=None, took=50, size=131072),
        ]
        requests = [latency.from_row(row, path="chat", arm="wait") for row in rows]
        return latency.group_requests(requests, lambda r: (r.size, r.setting))

    def test_one_panel_per_prompt_size_in_the_setting_order(self):
        panels = setting_panels(self._groups(), "mac-alone")
        self.assertEqual([panel.title for panel in panels], ["32K prompt", "128K prompt"])
        self.assertEqual([row.label for row in panels[0].rows], ["Mac alone", "Automatic", "49 layers"])

    def test_the_note_compares_with_the_mac_alone_where_it_was_run(self):
        panels = setting_panels(self._groups(), "mac-alone")
        by_label = {row.label: row for row in panels[0].rows}
        self.assertEqual(by_label["Mac alone"].note, "baseline")
        self.assertEqual(by_label["Automatic"].value_text, "32.1 s")
        self.assertEqual(by_label["Automatic"].note, "3.4× faster")
        # No Mac-alone request at 128K, so there is nothing to compare with.
        self.assertEqual([row.note for row in panels[1].rows], [""])

    def test_each_setting_keeps_one_colour_across_panels(self):
        panels = setting_panels(self._groups(), "mac-alone")
        colours = {row.label: row.series for panel in panels for row in panel.rows}
        self.assertEqual(colours["Mac alone"], "blue")
        self.assertNotEqual(colours["Automatic"], colours["49 layers"])


if __name__ == "__main__":
    unittest.main()