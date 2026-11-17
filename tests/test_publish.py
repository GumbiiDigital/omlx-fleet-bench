"""Tests for the publish step: manifest -> tables, reports, charts and README blocks."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bench import publish, quality_report, report

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL = "test-model"


def _speed_row(variant, size, repeat, tps, ttft_ms, peak_gb=20.0, valid=True, machine="box", runs=3):
    return {
        "machine": machine,
        "model": MODEL,
        "variant": variant,
        "prompt_size": size,
        "repeat_index": repeat,
        "runs_per_cell": runs,
        "metrics": {"processing_tps": tps, "ttft_ms": ttft_ms, "peak_memory_bytes": peak_gb * 2**30},
        "validity": {"valid": valid},
    }


def _quality_row(variant, task, sample, correct, content="answer", finish="stop", machine="box"):
    return {
        "machine": machine,
        "variant": variant,
        "task": task,
        "sample_id": sample,
        "correct": correct,
        "content": content,
        "finish_reason": finish,
        "status": "completed",
    }


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _marker(block_id):
    return f"<!-- BEGIN GENERATED: {block_id} -->\n<!-- END GENERATED: {block_id} -->\n"


class Workspace:
    """A small repository on disk: rows, a manifest and a README with markers."""

    def __init__(self, tmp):
        self.root = Path(tmp)
        speed = [
            _speed_row(variant, 8192, repeat, tps + repeat, ttft)
            for variant, tps, ttft in (("gpu", 300.0, 24000.0), ("spark", 900.0, 8000.0))
            for repeat in range(3)
        ]
        # Seven prompt sizes would be a long fixture; three carry the same shape.
        sweep = [
            _speed_row(variant, size, repeat, 300.0, ttft, runs=2)
            for variant, ttft in (("gpu", 24000.0), ("spark", 8000.0))
            for size in (1024, 8192, 32768)
            for repeat in range(2)
        ]
        # spark at 32K lost its second run, and a rerun replaced it: the cell only reaches
        # its planned 2 valid runs when both files are read.
        for row in sweep:
            if row["variant"] == "spark" and row["prompt_size"] == 32768 and row["repeat_index"] == 1:
                row["validity"]["valid"] = False
        sweep_rerun = [_speed_row("spark", 32768, 1, 300.0, 8000.0, runs=2)]
        kv = [
            _speed_row(variant, 32768, repeat, 300.0, 100000.0, peak_gb=peak)
            for variant, peak in (("native", 20.0), ("affine4", 15.0))
            for repeat in range(3)
        ]
        quality = []
        for variant, wrong in (("gpu", {"g0"}), ("affine4", {"g1"})):
            for index in range(40):
                sample = f"g{index}"
                quality.append(_quality_row(variant, "gsm8k", sample, sample not in wrong))
            quality.append(_quality_row(variant, "passkey", "p0", True))
        _write(self.root / "results/box/speed.jsonl", speed)
        _write(self.root / "results/box/sweep.jsonl", sweep)
        _write(self.root / "results/box/sweep-rerun.jsonl", sweep_rerun)
        _write(self.root / "results/box/kv.jsonl", kv)
        _write(self.root / "results/box/quality.jsonl", quality)
        _write(self.root / "results/box/reask.jsonl", [_quality_row("gpu", "gsm8k", "g0", True)])
        self.manifest = {
            "machines": [
                {
                    "label": "box",
                    "hardware": "Test Mac",
                    "helper": "Test helper",
                    "model": MODEL,
                    "speed": {
                        "files": ["results/box/speed.jsonl"],
                        "kind": "speed",
                        "baseline": "gpu",
                        "conditions": "cold",
                    },
                    "speed_sweep": {
                        "files": ["results/box/sweep.jsonl", "results/box/sweep-rerun.jsonl"],
                        "kind": "speed",
                        "baseline": "gpu",
                        "conditions": "cold, 2 runs per cell",
                    },
                    "kv_cache": {
                        "files": ["results/box/kv.jsonl"],
                        "kind": "speed",
                        "baseline": "native",
                        "conditions": "cold",
                    },
                    "quality": {
                        "files": ["results/box/quality.jsonl"],
                        "replace": ["results/box/reask.jsonl"],
                        "kind": "quality",
                        "baseline": "gpu",
                        "conditions": "same questions",
                    },
                }
            ]
        }
        self.save_manifest()
        (self.root / "README.md").write_text(
            "# Title\n\n"
            + _marker("speed box")
            + "\ntext\n\n"
            + _marker("speed-sweep box")
            + _marker("kv-cache box")
            + _marker("quality box"),
            encoding="utf-8",
        )

    def save_manifest(self):
        (self.root / publish.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def run(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return publish.main(["--root", str(self.root), *args])


class PublishTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = Workspace(self._tmp.name)

    def test_blocks_carry_the_numbers_from_the_rows(self):
        _, blocks = publish.build(self.ws.root)
        self.assertEqual(set(blocks), {"speed box", "speed-sweep box", "kv-cache box", "quality box"})
        self.assertIn("| GPU only | 24.0 s |", blocks["speed box"])
        self.assertIn("| + Spark helper | 8.0 s · 3.0× |", blocks["speed box"])
        self.assertIn("| + Spark helper | 901 |", blocks["speed box"])
        self.assertIn("| Affine4 KV | 15.0 GB · −25.0% | 100.0 s · +0.0% |", blocks["kv-cache box"])
        # gpu: g0 wrong, then re-asked right -> 40 of 40. affine4: g1 wrong -> 39 of 40, one answer lost.
        self.assertIn("| GPU only | 40 · 100.0% | 1 | baseline | 0 |", blocks["quality box"])
        self.assertIn("| Affine4 KV | 39 · 97.5% | 1 | 1 lost, 0 gained (of 40) | 0 |", blocks["quality box"])

    def test_the_sweep_table_has_one_line_per_prompt_size(self):
        _, blocks = publish.build(self.ws.root)
        sweep = blocks["speed-sweep box"]
        for row in ("| 1K | 24.0 s | 8.0 s | 3.0× |", "| 8K | 24.0 s | 8.0 s | 3.0× |", "| 32K | 24.0 s | 8.0 s | 3.0× |"):
            self.assertIn(row, sweep)
        self.assertIn("Mean of 2 valid runs per cell.", sweep)
        self.assertNotIn("Prefill speed", sweep)

    def test_outputs_cover_reports_and_both_chart_themes(self):
        outputs, _ = publish.build(self.ws.root)
        self.assertEqual(
            sorted(outputs),
            sorted(
                [f"charts/box-{name}-{theme}.svg" for name in ("ttft", "ttft-sweep", "kv-memory", "quality") for theme in ("light", "dark")]
                + [f"reports/box/{name}.md" for name in ("speed", "speed-sweep", "kv-cache", "quality")]
            ),
        )

    def test_write_then_check_passes_and_a_changed_row_fails(self):
        self.assertEqual(self.ws.run("--check"), 1)
        self.assertEqual(self.ws.run(), 0)
        self.assertEqual(self.ws.run("--check"), 0)
        self.assertIn("| GPU only | 24.0 s |", (self.ws.root / "README.md").read_text(encoding="utf-8"))

        rows = report.load_rows([self.ws.root / "results/box/speed.jsonl"])
        rows[0]["metrics"]["ttft_ms"] = 30000.0
        _write(self.ws.root / "results/box/speed.jsonl", rows)
        self.assertEqual(self.ws.run("--check"), 1)

    def test_text_outside_the_markers_is_kept(self):
        self.ws.run()
        readme = (self.ws.root / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# Title\n"))
        self.assertIn("\ntext\n", readme)

    def test_missing_marker_is_an_error(self):
        (self.ws.root / "README.md").write_text(_marker("speed box"), encoding="utf-8")
        self.assertEqual(self.ws.run(), 2)

    def test_marker_that_nothing_builds_is_an_error(self):
        readme = self.ws.root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + _marker("speed other-box"), encoding="utf-8")
        self.assertEqual(self.ws.run(), 2)

    def test_missing_result_file_is_an_error(self):
        self.ws.manifest["machines"][0]["speed"]["files"] = ["results/box/absent.jsonl"]
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)

    def test_incomplete_cell_is_an_error(self):
        rows = report.load_rows([self.ws.root / "results/box/speed.jsonl"])
        rows[0]["validity"]["valid"] = False
        _write(self.ws.root / "results/box/speed.jsonl", rows)
        self.assertEqual(self.ws.run(), 2)

    def test_a_sweep_cell_reads_its_runs_across_both_files(self):
        # sweep.jsonl alone gives spark at 32K one valid run of two.
        outputs, _ = publish.build(self.ws.root)
        report_text = outputs["reports/box/speed-sweep.md"]
        self.assertIn("| box | test-model | spark | 32768 | 2/2 |", report_text)

        self.ws.manifest["machines"][0]["speed_sweep"]["files"] = ["results/box/sweep.jsonl"]
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)

    def test_a_sweep_kind_that_does_not_match_its_builder_is_an_error(self):
        self.ws.manifest["machines"][0]["speed_sweep"]["kind"] = "quality"
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)

    def test_a_sweep_without_a_second_setup_is_an_error(self):
        rows = report.load_rows([self.ws.root / "results/box/sweep.jsonl"])
        _write(self.ws.root / "results/box/sweep.jsonl", [r for r in rows if r["variant"] == "gpu"])
        _write(self.ws.root / "results/box/sweep-rerun.jsonl", [])
        self.assertEqual(self.ws.run(), 2)

    def test_a_study_that_was_not_run_is_left_out(self):
        del self.ws.manifest["machines"][0]["kv_cache"]
        self.ws.save_manifest()
        _, blocks = publish.build(self.ws.root)
        self.assertEqual(set(blocks), {"speed box", "speed-sweep box", "quality box"})


class SpliceTest(unittest.TestCase):
    def test_replaces_old_block_content(self):
        text = "a\n<!-- BEGIN GENERATED: x -->\nold\nlines\n<!-- END GENERATED: x -->\nb\n"
        self.assertEqual(
            publish.splice(text, {"x": "new"}),
            "a\n<!-- BEGIN GENERATED: x -->\nnew\n<!-- END GENERATED: x -->\nb\n",
        )

    def test_splice_is_stable(self):
        text = "<!-- BEGIN GENERATED: x -->\n<!-- END GENERATED: x -->\n"
        once = publish.splice(text, {"x": "| a |\n| b |"})
        self.assertEqual(publish.splice(once, {"x": "| a |\n| b |"}), once)


class ChangesAgainstTest(unittest.TestCase):
    def test_counts_lost_gained_and_different_text(self):
        rows = [
            _quality_row("gpu", "mmlu", "a", True, "A"),
            _quality_row("gpu", "mmlu", "b", False, "B"),
            _quality_row("gpu", "mmlu", "c", True, "C"),
            _quality_row("ane", "mmlu", "a", False, "D"),
            _quality_row("ane", "mmlu", "b", True, "A"),
            _quality_row("ane", "mmlu", "c", True, "C"),
            _quality_row("ane", "mmlu", "only-here", True, "A"),
        ]
        changes = quality_report.changes_against(rows, "gpu")
        self.assertEqual(set(changes), {("ane", "mmlu")})
        self.assertEqual(changes[("ane", "mmlu")], quality_report.AnswerChanges(3, 1, 1, 2))


class CommittedResultsTest(unittest.TestCase):
    """The tables, reports and charts in this repository match its raw rows."""

    def test_publish_check_passes_on_the_repository(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = publish.main(["--check", "--root", str(REPO_ROOT)])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
