"""Tests for the publish step: manifest -> page blocks, reports and charts."""

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
    """One many-users row: a request of a group, with the group's own figures beside it."""
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


def _study_of(block_id):
    """The manifest key a block id belongs to: 'many-users box' -> 'many_users'."""
    return block_id.split(" ")[0].replace("-", "_")


def _write_pages(root, block_ids, readme_text="# Title\n\ntext\n"):
    """Write a page for every target in publish's own layout, with the markers of its blocks.

    The fixture asks publish where each block belongs instead of naming a page itself, so a change
    to the layout cannot leave the fixture checking a page the real tree does not have.
    """
    pages = {}
    for block_id in block_ids:
        pages.setdefault(publish.PAGES[_study_of(block_id)], []).append(block_id)
    for page, ids in pages.items():
        path = root / page
        path.parent.mkdir(parents=True, exist_ok=True)
        text = readme_text if page == publish.README else f"# {Path(page).stem}\n\nTODO(stage B): page text\n\n"
        path.write_text(text + "\n".join(_marker(block_id) for block_id in ids), encoding="utf-8")


class Workspace:
    """A small repository on disk: rows, a manifest and the pages that hold the blocks."""

    BLOCKS = ["headline", "speed box", "speed-sweep box", "kv-cache box", "quality box"]

    def __init__(self, tmp):
        self.root = Path(tmp)
        speed = [
            _speed_row(variant, size, repeat, tps + repeat, ttft)
            for variant, tps, ttft in (("gpu", 300.0, 24000.0), ("spark", 900.0, 8000.0))
            for size in (8192, 32768)
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
                    "display_name": "Test Mac",
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
                        "conditions": "cold, 2 runs per row",
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
        _write_pages(self.root, self.BLOCKS)

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
        self.assertEqual(set(blocks), set(self.ws.BLOCKS))
        speed = blocks["speed box"].body
        self.assertIn("### Test Mac", speed)
        self.assertIn("| Mac alone | 24.0 s | 24.0 s |", speed)
        self.assertIn("| + Spark helper | 8.0 s · 3.0× | 8.0 s · 3.0× |", speed)
        self.assertIn("| + Spark helper | 901 | 901 |", speed)
        self.assertIn("| 4-bit prompt memory | 15.0 GB · −25.0% | 100.0 s · +0.0% |", blocks["kv-cache box"].body)
        # gpu: g0 wrong, then re-asked right -> 40 of 40. 4-bit: g1 wrong -> 39 of 40, one answer lost.
        self.assertIn("| Mac alone | 40 · 100.0% | 1 | baseline |", blocks["quality box"].body)
        self.assertIn(
            "| 4-bit prompt memory | 39 · 97.5% | 1 | 1 right answers became wrong, "
            "0 wrong answers became right (of 40) |",
            blocks["quality box"].body,
        )

    def test_each_block_goes_to_the_page_the_layout_names(self):
        _, blocks = publish.build(self.ws.root)
        self.assertEqual(blocks["speed box"].page, "docs/speed.md")
        self.assertEqual(blocks["speed-sweep box"].page, "docs/speed.md")
        self.assertEqual(blocks["kv-cache box"].page, "docs/memory.md")
        self.assertEqual(blocks["quality box"].page, "docs/answer-quality.md")
        self.assertEqual(blocks["headline"].page, "README.md")

    def test_the_headline_block_holds_both_setups_and_the_speed_up(self):
        _, blocks = publish.build(self.ws.root)
        body = blocks["headline"].body
        self.assertIn("| Prompt size | Mac alone | Mac + Spark | Faster by |", body)
        self.assertIn("| 8K | 24.0 s | 8.0 s | 3.0× |", body)
        self.assertIn('src="charts/headline-light.svg"', body)

    def test_the_sweep_table_has_one_line_per_prompt_size(self):
        _, blocks = publish.build(self.ws.root)
        sweep = blocks["speed-sweep box"].body
        for row in ("| 1K | 24.0 s | 8.0 s | 3.0× |", "| 8K | 24.0 s | 8.0 s | 3.0× |", "| 32K | 24.0 s | 8.0 s | 3.0× |"):
            self.assertIn(row, sweep)
        self.assertIn("the mean of 2 valid runs", sweep)
        self.assertNotIn("Reading the prompt, in tokens per second", sweep)

    def test_outputs_cover_reports_pages_and_both_chart_themes(self):
        outputs, _ = publish.build(self.ws.root)
        expected = (
            [f"charts/box-{name}-{theme}.svg" for name in ("ttft", "ttft-sweep", "kv-memory", "quality") for theme in ("light", "dark")]
            + [f"charts/headline-{theme}.svg" for theme in ("light", "dark")]
            + [f"reports/box/{name}.md" for name in ("speed", "speed-sweep", "kv-cache", "quality")]
        )
        self.assertEqual(sorted(outputs), sorted(expected))

    def test_write_then_check_passes_and_a_changed_row_fails(self):
        self.assertEqual(self.ws.run("--check"), 1)
        self.assertEqual(self.ws.run(), 0)
        self.assertEqual(self.ws.run("--check"), 0)
        page = (self.ws.root / "docs/speed.md").read_text(encoding="utf-8")
        self.assertIn("| Mac alone | 24.0 s | 24.0 s |", page)
        self.assertTrue((self.ws.root / "docs/memory.md").is_file())

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

    def test_a_page_that_holds_a_block_and_is_missing_is_an_error(self):
        (self.ws.root / "docs/memory.md").unlink()
        self.assertEqual(self.ws.run(), 2)

    def test_a_marker_on_a_page_the_layout_does_not_name_for_it_is_an_error(self):
        # The speed block belongs on docs/speed.md; the same markers on another page must not pass.
        memory = self.ws.root / "docs/memory.md"
        memory.write_text(memory.read_text(encoding="utf-8") + _marker("speed box"), encoding="utf-8")
        self.assertEqual(self.ws.run("--check"), 2)
        self.assertEqual(self.ws.run(), 2)

    def test_a_marker_on_a_page_with_no_block_at_all_is_an_error(self):
        page = self.ws.root / "docs/run-it.md"
        page.write_text("# Run it\n\n" + _marker("speed box"), encoding="utf-8")
        self.assertEqual(self.ws.run(), 2)

    def test_a_page_with_no_block_and_no_marker_is_left_alone(self):
        page = self.ws.root / "docs/method.md"
        page.write_text("# Method\n\nHow it was measured.\n", encoding="utf-8")
        self.assertEqual(self.ws.run(), 0)
        _, blocks = publish.build(self.ws.root)
        self.assertNotIn("docs/method.md", publish.splice_pages(self.ws.root, blocks))
        self.assertEqual(page.read_text(encoding="utf-8"), "# Method\n\nHow it was measured.\n")

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
        self.assertIn("| box | test-model | + Spark helper | 32768 | 2/2 |", report_text)

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
        self.assertEqual(set(blocks), {"headline", "speed box", "speed-sweep box", "quality box"})

    def test_a_machine_without_a_display_name_is_an_error(self):
        del self.ws.manifest["machines"][0]["display_name"]
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)


class RequestWorkspace:
    """A repository that holds the two request studies: what a request waited, in which round."""

    BLOCKS = ["helper-ready box", "helper-layers box"]

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
                    "display_name": "Test Mac",
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
        _write_pages(self.root, self.BLOCKS)

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

    def test_the_helper_ready_table_has_one_line_per_path_and_round(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"].body
        self.assertIn("| chat | Started at once | 0.0 | 109.70 to 109.76 s | 0 of 2 |", block)
        self.assertIn("| chat | Waited for the helper | 20.1 | 29.31 to 29.93 s | 2 of 2 |", block)
        self.assertIn("| speed test | Started at once | 0.0 | 29.50 to 30.00 s | 2 of 2 |", block)

    def test_the_block_says_which_round_ran_on_the_mac_alone(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"].body
        # Only the chat round that started at once ran at the speed of the Mac alone: 0 of 2 on the helper.
        self.assertIn("| chat | Started at once | 0.0 | 109.70 to 109.76 s | 0 of 2 |", block)
        self.assertNotIn("| chat | Waited for the helper | 20.1 | 29.31 to 29.93 s | 0 of 2 |", block)
        # The speed-test row has no answer of its own, so answers are counted where they exist.
        self.assertIn("Every request read its prompt cold; 4 of 4 answers were correct.", block)

    def test_the_state_at_the_start_is_named_for_every_round(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"].body
        self.assertIn("chat, Started at once: not ready yet, still connecting (2 of 2)", block)
        self.assertIn("speed test, Started at once: not ready yet, still starting (2 of 2)", block)
        self.assertIn("chat, Waited for the helper: ready (2 of 2)", block)

    def test_the_rows_a_flag_marks_not_valid_are_named_in_the_block(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-ready box"].body
        self.assertIn(
            "These 2 started before the helper was ready, so we do not count them. "
            "They are the speed test / Started at once rows",
            block,
        )
        self.assertNotIn("helper_ready_at_start", block)

    def test_the_not_valid_line_says_what_the_waits_measured(self):
        _, blocks = publish.build(self.ws.root)
        line = next(l for l in blocks["helper-ready box"].body.splitlines() if "do not count" in l)
        # These rows began while the helper was starting and still came back in about 30 s: helper
        # speed, not the Mac alone.
        self.assertIn("started before the helper was ready", line)
        self.assertIn("ran at helper speed (29.50 to 30.00 s)", line)
        self.assertNotIn("Mac alone", line)
        self.assertNotIn("read the whole prompt", line)

    def test_the_layer_table_gives_a_mean_and_a_range_for_each_prompt_size(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["helper-layers box"].body
        self.assertIn("| Mac alone | 109.7 s, 109.69 to 109.73 s | not run | none | baseline |", block)
        self.assertIn("| Automatic | 31.5 s, 29.42 to 33.62 s | 178.7 s (3.0 min), 177.96 to 179.42 s |", block)
        self.assertIn("| 49 layers | 29.7 s, 29.50 to 29.91 s | 166.1 s (2.8 min), 165.71 to 166.41 s | 49 | 3.7× |", block)

    def test_the_layer_table_names_every_layer_count_the_helper_took(self):
        _, blocks = publish.build(self.ws.root)
        self.assertIn("32K: 49; 128K: 50, 49", blocks["helper-layers box"].body)

    def test_outputs_cover_both_reports_and_one_chart_pair(self):
        outputs, _ = publish.build(self.ws.root)
        expected = (
            [f"charts/box-helper-layers-{theme}.svg" for theme in ("light", "dark")]
            + ["reports/box/helper-ready.md", "reports/box/helper-layers.md"]
        )
        self.assertEqual(sorted(outputs), sorted(expected))

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

    def test_a_block_with_no_marker_pair_names_the_page(self):
        with self.assertRaises(publish.PublishError) as caught:
            publish.splice("no markers here\n", {"x": "body"}, "docs/speed.md")
        self.assertIn("docs/speed.md", str(caught.exception))


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
    """The pages, tables, reports and charts in this repository match its raw rows."""

    def test_publish_check_passes_on_the_repository(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = publish.main(["--check", "--root", str(REPO_ROOT)])
        self.assertEqual(code, 0, out.getvalue())


class ManyUsersWorkspace:
    """A repository that holds a many-users study: groups of requests in two setups."""

    BLOCKS = ["many-users box"]

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
                    "display_name": "Test Mac",
                    "hardware": "Test Mac",
                    "helper": "Test helper",
                    "model": MODEL,
                    "many_users": {
                        "kind": "request",
                        "files": ["results/box/waves.jsonl"],
                        "conditions": "cold, every user of a group sends at the same moment",
                    },
                }
            ]
        }
        (self.root / publish.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")
        _write_pages(self.root, self.BLOCKS)

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

    def test_the_table_has_one_line_per_prompt_size_and_user_count(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"].body
        self.assertIn("| Prompt size | Users | Mac alone | Mac + Spark | Faster by |", block)
        self.assertIn("| 4K | 1 | 10.5 s | 8.5 s | 1.24× |", block)
        self.assertIn("Mean of 2 groups per case, at 1 and 2 users per group.", block)
        self.assertEqual(sum(1 for line in block.splitlines() if line.startswith("| 4K") or line.startswith("| 32K")), 4)

    def test_the_block_says_why_a_group_is_left_out_of_a_mean(self):
        _, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"].body
        self.assertIn("If one request in a group fails our checks, we leave out the whole group.", block)
        self.assertNotIn("left out of the group means as a whole", block)

    def test_a_flagged_row_is_counted_and_named_and_left_out_of_the_means(self):
        rows = [dict(row) for row in self.ws.rows]
        for row in rows:
            if row["target_tokens"] == 32768 and row["users"] == 2 and row["helper_on"] and row["wave"] == 1:
                row["validity"] = {**row["validity"], "valid": False, "helper_served_proven": False}
        self.ws.rewrite(rows)
        _, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"].body
        # The group that holds the flagged request has no whole-group figure: the mean is round 0 alone.
        self.assertIn("| 32K | 2 | 20.5 s | 16.0 s | 1.28× |", block)
        self.assertIn("A mean rests on 1 to 2 groups per case, at 1 and 2 users per group", block)
        self.assertIn("Requests marked not valid by a check", block)
        self.assertIn("2 · helper_served_proven", block)
        self.assertIn("All 24 requests read their prompt cold and got a correct answer.", block)

    def _break(self, keep, **fields):
        """Write the rows back with the matching ones marked not valid."""
        rows = []
        for row in self.ws.rows:
            if all(row[key] == value for key, value in fields.items()):
                row = dict(row)
                row["validity"] = {**row["validity"], "valid": False, **keep}
            rows.append(row)
        self.ws.rewrite(rows)

    def test_a_group_without_a_fully_valid_round_prints_dashes_and_the_publish_goes_on(self):
        self._break({"wave_answered": False}, target_tokens=4096, users=2, helper_on=True)
        outputs, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"].body
        # No request of the case is valid, so nothing in the row can be worked out but its counts.
        self.assertIn("| 4K | 2 | 20.5 s | - | - |", block)
        # The rest of the study is untouched, table and chart alike.
        self.assertIn("| 4K | 1 | 10.5 s | 8.5 s | 1.24× |", block)
        self.assertIn("A mean rests on 0 to 2 groups per case", block)
        self.assertEqual(
            sorted(outputs),
            sorted(
                [f"charts/box-many-users-{theme}.svg" for theme in ("light", "dark")]
                + ["reports/box/many-users.md"]
            ),
        )

    def test_a_helper_case_whose_mac_alone_case_has_no_valid_round_has_no_speed_up(self):
        self._break({"wave_answered": False}, target_tokens=4096, users=2, helper_on=False)
        _, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"].body
        self.assertIn("| 4K | 2 | - | 16.5 s | - |", block)
        # The helper case itself is intact, so its own figures stand and only the speed-up is missing.
        self.assertIn("| 4K | 1 | 10.5 s | 8.5 s | 1.24× |", block)

    def test_a_study_with_no_valid_group_at_all_still_builds_its_table_and_report(self):
        self._break({"wave_answered": False})
        outputs, blocks = publish.build(self.ws.root)
        block = blocks["many-users box"].body
        self.assertIn("| 4K | 1 | - | - | - |", block)
        self.assertIn("No cell has a fully valid group, so every mean in the table is `-`.", block)
        self.assertEqual(sorted(outputs), ["reports/box/many-users.md"])
        self.assertEqual(self.ws.run(), 0)
        self.assertEqual(self.ws.run("--check"), 0)

    def test_outputs_cover_the_report_and_one_chart_pair(self):
        outputs, _ = publish.build(self.ws.root)
        expected = (
            [f"charts/box-many-users-{theme}.svg" for theme in ("light", "dark")]
            + ["reports/box/many-users.md"]
        )
        self.assertEqual(sorted(outputs), sorted(expected))
        report_text = outputs["reports/box/many-users.md"]
        self.assertIn("| Mac alone | 4K | 1 | 0 | 1 | 1 |", report_text)

    def test_write_then_check_passes(self):
        self.assertEqual(self.ws.run(), 0)
        self.assertEqual(self.ws.run("--check"), 0)

    def test_a_study_kind_that_does_not_match_its_builder_is_an_error(self):
        self.ws.manifest["machines"][0]["many_users"]["kind"] = "speed"
        self.ws.save_manifest()
        self.assertEqual(self.ws.run(), 2)

    def test_a_study_with_one_setup_is_an_error(self):
        self.ws.rewrite([row for row in self.ws.rows if not row["helper_on"]])
        self.assertEqual(self.ws.run(), 2)

    def test_a_case_without_a_group_is_an_error(self):
        self.ws.rewrite(
            [row for row in self.ws.rows if not (row["target_tokens"] == 4096 and row["users"] == 2 and row["helper_on"])]
        )
        self.assertEqual(self.ws.run(), 2)


if __name__ == "__main__":
    unittest.main()
