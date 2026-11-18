"""Tests for the publish step: manifest -> tables, reports, charts and README blocks."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bench import latency, publish, quality_report, report

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


def _wave_row(size, users, wave, index, helper, wall, machine="box"):
    """One many-users row: a request of a wave, with the wave's own figures beside it."""
    return {
        "machine": machine,
        "helper_on": helper,
        "helper_state": "ready" if helper else None,
        "helper_wait_s": 0.0,
        "desired_settings": {"prefill_helper_layers": None},
        "users": users,
        "wave": wave,
        "wave_id": f"{'spark' if helper else 'gpu'}-{size}-u{users}-w{wave}",
        "user_index": index,
        "target_tokens": size,
        "task": "many_users",
        "status": "completed",
        "correct": True,
        "usage": {"cached_tokens": 0, "prompt_tokens": 4000},
        "server_timing": {"time_to_first_token": wall / 2},
        "wave_wall_s": wall,
        "validity": {
            "valid": True,
            "wave_answered": True,
            "status_completed": True,
            "cached_tokens_zero": True,
            "helper_ready_at_wave_start": True,
            "helper_served_proven": True,
            "helper_served": True,
        },
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


class RequestWorkspace:
    """A repository that holds the two request studies: what a request waited, in which arm."""

    def __init__(self, tmp):
        self.root = Path(tmp)

        def chat(ttft, *, size=32768, helper=True, ask=None, took=None, state="ready", wait=0.0):
            return {
                "machine": "box",
                "helper_on": helper,
                "helper_state": state if helper else None,
                "helper_wait_s": wait,
                "helper_layers": took,
                "desired_settings": {"prefill_helper_layers": ask},
                "target_tokens": size,
                "status": "completed",
                "correct": True,
                "usage": {"cached_tokens": 0},
                "server_timing": {"time_to_first_token": ttft},
            }

        def speed(ttft_ms, *, state="ready", wait=0.0, checks=None):
            return {
                "machine": "box",
                "helper_on": True,
                "helper_state": state,
                "helper_wait_s": wait,
                "helper_layers": 49,
                "desired_settings": {"prefill_helper_layers": None},
                "prompt_size": 32768,
                "metrics": {"ttft_ms": ttft_ms},
                "log": {"cached_tokens": 0},
                "validity": {"valid": not checks, **(checks or {})},
            }

        _write(self.root / "results/box/chat-nowait.jsonl", [chat(109.70, state="connecting", took=49), chat(109.76, state="connecting", took=49)])
        _write(self.root / "results/box/chat-wait.jsonl", [chat(29.31, wait=20.0, took=49), chat(29.93, wait=20.2, took=49)])
        _write(
            self.root / "results/box/speed-nowait.jsonl",
            [
                speed(29500.0, state="starting", checks={"helper_ready_at_start": False}),
                speed(30000.0, state="starting", checks={"helper_ready_at_start": False}),
            ],
        )
        _write(
            self.root / "results/box/layers.jsonl",
            [
                chat(109.69, helper=False, size=32768),
                chat(109.73, helper=False, size=32768),
                chat(29.42, took=49, size=32768),
                chat(33.62, took=49, size=32768),
                chat(29.50, ask=49, took=49, size=32768),
                chat(29.91, ask=49, took=49, size=32768),
                chat(177.96, took=50, size=131072),
                chat(179.42, took=49, size=131072),
                chat(165.71, ask=49, took=49, size=131072),
                chat(166.41, ask=49, took=49, size=131072),
            ],
        )
        self.manifest = {
            "machines": [
                {
                    "label": "box",
                    "hardware": "Test Mac",
                    "helper": "Test helper",
                    "model": MODEL,
                    "helper_ready": {
                        "kind": "request",
                        "arms": [
                            {"path": "chat", "arm": "no wait", "file": "results/box/chat-nowait.jsonl"},
                            {"path": "chat", "arm": "wait", "file": "results/box/chat-wait.jsonl"},
                            {"path": "speed test", "arm": "no wait", "file": "results/box/speed-nowait.jsonl"},
                        ],
                        "conditions": "cold",
                    },
                    "helper_layers": {
                        "kind": "request",
                        "arms": [{"path": "chat", "arm": "wait", "file": "results/box/layers.jsonl"}],
                        "conditions": "cold",
                    },
                }
            ]
        }
        (self.root / publish.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.root / "README.md").write_text(
            "# Title\n\n" + _marker("helper-ready box") + _marker("helper-layers box"),
            encoding="utf-8",
        )

    def save_manifest(self):
        (self.root / publish.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def run(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return publish.main(["--root", str(self.root), *args])


class RequestStudyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = RequestWorkspace(self._tmp.name)

    def test_the_helper_ready_table_has_one_line_per_arm(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"]
        self.assertIn("| chat | no wait | 2 | connecting (2 of 2) | no validity marks | 0.0 s | 109.70 to 109.76 s | 0 of 2 |", block)
        self.assertIn("| chat | wait | 2 | ready (2 of 2) | no validity marks | 20.1 s | 29.31 to 29.93 s | 2 of 2 |", block)
        self.assertIn("| speed test | no wait | 2 | starting (2 of 2) |", block)

    def test_the_rows_a_flag_marks_not_valid_are_named_in_the_table(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"]
        self.assertIn("| speed test | no wait | 2 | starting (2 of 2) | 2 · helper_ready_at_start |", block)
        # The chat rows carry no validity block, so the cell says that instead of a zero a reader
        # would take for "every row passed".
        self.assertIn("| chat | no wait | 2 | connecting (2 of 2) | no validity marks |", block)
        self.assertNotIn("| chat | no wait | 2 | connecting (2 of 2) | 0 |", block)

    def test_the_helper_ready_block_says_which_arm_ran_on_the_mac_alone(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"]
        self.assertIn("chat, no wait: 2 of 2 requests ran at the speed of the Mac alone.", block)
        self.assertNotIn("chat, wait: 2 of 2 requests ran at the speed of the Mac alone.", block)
        # The speed-test row has no answer of its own, so answers are counted where they exist.
        self.assertIn("Every request read its prompt cold; 4 of 4 answers were correct.", block)

    def test_the_not_valid_line_says_what_the_waits_measured(self):
        _, blocks = publish.build(self.ws.root)
        line = next(l for l in blocks["helper-ready box"].splitlines() if "helper_ready_at_start" in l and "marked" in l)
        # These rows began at `starting` and still came back in about 30 s: helper speed, not Mac alone.
        self.assertIn("began at helper state starting (2 of 2)", line)
        self.assertIn("ran at helper speed (29.50 to 30.00 s)", line)
        self.assertNotIn("Mac alone", line)
        self.assertNotIn("read the whole prompt", line)

    def test_the_layer_table_gives_a_mean_and_a_range_for_each_prompt_size(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-layers box"]
        self.assertIn("| Mac alone | 109.7 s (109.69 to 109.73) | not run | none | baseline |", block)
        self.assertIn("| Automatic | 31.5 s (29.42 to 33.62) | 178.7 s (177.96 to 179.42) |", block)
        self.assertIn("| 49 layers | 29.7 s (29.50 to 29.91) | 166.1 s (165.71 to 166.41) | 49 | 3.7× |", block)

    def test_the_layer_table_names_every_layer_count_the_helper_took(self):
        _, blocks = publish.build(self.ws.root)
        self.assertIn("32K: 49; 128K: 50, 49", blocks["helper-layers box"])

    def test_outputs_cover_both_reports_and_one_chart_pair(self):
        outputs, _ = publish.build(self.ws.root)
        self.assertEqual(
            sorted(outputs),
            sorted(
                [f"charts/box-helper-layers-{theme}.svg" for theme in ("light", "dark")]
                + ["reports/box/helper-ready.md", "reports/box/helper-layers.md"]
            ),
        )

    def test_write_then_check_passes(self):
        self.assertEqual(self.ws.run(), 0)
        self.assertEqual(self.ws.run("--check"), 0)

    def test_a_request_study_kind_that_does_not_match_its_builder_is_an_error(self):
        self.ws.manifest["machines"][0]["helper_ready"]["kind"] = "speed"
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)

    def test_a_missing_arm_file_is_an_error(self):
        self.ws.manifest["machines"][0]["helper_layers"]["arms"][0]["file"] = "results/box/absent.jsonl"
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)


class NotValidLineTest(unittest.TestCase):
    """The sentence about the flagged rows follows the measured waits, not the state alone."""

    def _flagged(self, ttfts, state="starting"):
        return latency.Waits(
            [
                latency.Request(
                    machine="box",
                    path="p",
                    arm="a",
                    size=32768,
                    setting="automatic",
                    ttft_s=ttft,
                    helper_on=True,
                    helper_state=state,
                    helper_wait_s=0.0,
                    helper_layers=49,
                    cached_tokens=0,
                    correct=None,
                    failed=("helper_ready_at_start",),
                    checks_recorded=True,
                )
                for ttft in ttfts
            ]
        )

    def test_rows_that_came_back_fast_are_called_helper_speed(self):
        line = publish._not_valid_line("speed test", "no wait", self._flagged([29.5, 30.0]), {32768: 109.7})
        self.assertIn("ran at helper speed (29.50 to 30.00 s)", line)
        self.assertNotIn("Mac alone", line)

    def test_rows_that_took_the_mac_alone_wait_are_called_that(self):
        line = publish._not_valid_line(
            "chat", "no wait", self._flagged([109.7, 109.8], state="connecting"), {32768: 109.7}
        )
        self.assertIn("ran at the speed of the Mac alone (109.70 to 109.80 s)", line)

    def test_a_mixed_set_says_how_many_ran_on_the_helper(self):
        line = publish._not_valid_line("p", "a", self._flagged([29.5, 109.8]), {32768: 109.7})
        self.assertIn("1 of 2 ran at helper speed", line)


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


class ManyUsersWorkspace:
    """A repository that holds a many-users study: waves of requests in two arms."""

    def __init__(self, tmp):
        self.root = Path(tmp)
        self.rows = []
        for size in (4096, 32768):
            for users in (1, 2):
                for helper in (False, True):
                    for wave in range(2):
                        wall = (10.0 if not helper else 8.0) * users + wave
                        for index in range(users):
                            self.rows.append(_wave_row(size, users, wave, index, helper, wall))
        _write(self.root / "results/box/waves.jsonl", self.rows)
        self.manifest = {
            "machines": [
                {
                    "label": "box",
                    "hardware": "Test Mac",
                    "helper": "Test helper",
                    "model": MODEL,
                    "many_users": {
                        "kind": "request",
                        "files": ["results/box/waves.jsonl"],
                        "conditions": "cold, every user of a wave sends at the same moment",
                    },
                }
            ]
        }
        (self.root / publish.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.root / "README.md").write_text("# Title\n\n" + _marker("many-users box"), encoding="utf-8")

    def rewrite(self, rows):
        _write(self.root / "results/box/waves.jsonl", rows)

    def save_manifest(self):
        (self.root / publish.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def run(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return publish.main(["--root", str(self.root), *args])


class ManyUsersStudyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws = ManyUsersWorkspace(self._tmp.name)

    def test_the_table_has_one_line_per_prompt_size_user_count_and_arm(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"]
        self.assertIn("| 4K | 1 | Mac alone | 2 | 2 | 5.25 s (5.00 to 5.50) | 10.5 s | 382 | baseline |", block)
        self.assertIn("| 4K | 1 | With helper | 2 | 2 |", block)
        self.assertIn("Mean of 2 waves per cell, at 1 and 2 users per wave.", block)
        self.assertEqual(sum(1 for line in block.splitlines() if line.startswith("| 4K") or line.startswith("| 32K")), 8)

    def test_the_speed_up_is_the_mac_alone_wave_over_the_helper_wave(self):
        _, blocks = publish.build(self.ws.root)
        self.assertIn("| 4K | 1 | With helper | 2 | 2 | 4.25 s (4.00 to 4.50) | 8.5 s | 472 | 1.24× |", blocks["many-users box"])

    def test_a_flagged_row_is_counted_and_named_and_left_out_of_the_means(self):
        rows = [dict(row) for row in self.ws.rows]
        for row in rows:
            if row["target_tokens"] == 32768 and row["users"] == 2 and row["helper_on"] and row["wave"] == 1:
                row["validity"] = {**row["validity"], "valid": False, "helper_served_proven": False}
        self.ws.rewrite(rows)
        _, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"]
        self.assertIn("| 32K | 2 | With helper | 4 | 2 |", block)
        # The wave that holds the flagged request has no whole-wave figure: the mean is wave 0 alone.
        self.assertIn("| 32K | 2 | With helper | 4 | 2 | 8.00 s (8.00 to 8.00) | 16.0 s | 500 |", block)
        self.assertIn("Requests marked not valid by a check", block)
        self.assertIn("2 · helper_served_proven", block)
        self.assertIn("All 24 requests read their prompt cold and got a correct answer.", block)

    def test_outputs_cover_the_report_and_one_chart_pair(self):
        outputs, _ = publish.build(self.ws.root)
        self.assertEqual(
            sorted(outputs),
            sorted(
                [f"charts/box-many-users-{theme}.svg" for theme in ("light", "dark")]
                + ["reports/box/many-users.md"]
            ),
        )
        report_text = outputs["reports/box/many-users.md"]
        self.assertIn("| Mac alone | 4K | 1 | 0 | 1 | 1 |", report_text)

    def test_write_then_check_passes(self):
        self.assertEqual(self.ws.run(), 0)
        self.assertEqual(self.ws.run("--check"), 0)

    def test_a_study_kind_that_does_not_match_its_builder_is_an_error(self):
        self.ws.manifest["machines"][0]["many_users"]["kind"] = "speed"
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)

    def test_a_study_with_one_arm_is_an_error(self):
        self.ws.rewrite([row for row in self.ws.rows if not row["helper_on"]])
        self.assertEqual(self.ws.run(), 2)

    def test_a_cell_without_a_wave_is_an_error(self):
        self.ws.rewrite(
            [row for row in self.ws.rows if not (row["target_tokens"] == 4096 and row["users"] == 2 and row["helper_on"])]
        )
        self.assertEqual(self.ws.run(), 2)


if __name__ == "__main__":
    unittest.main()
