"""Tests for bench/readable.py, and for the reader pages it guards.

The checker runs on the whole of every page a reader lands on, hand text and generated blocks alike,
because a hard word or a six-column table is as much a fault in the prose as in a block. The front
door is also held to a length a person will read.
"""

import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from bench import publish, readable

REPO_ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "{http://www.w3.org/2000/svg}"
# The pages a reader lands on: the front door, and the topic pages beside it.
PAGES = [REPO_ROOT / "README.md"] + sorted((REPO_ROOT / "docs").glob("*.md"))
# The page a new contributor reads first, written for a person like the rest.
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
# A front door holds the answer and the way in, not a wall of notes.
MAX_README_LINES = 150

# A Markdown link: the text in brackets, then the target, and an optional title after it.
LINK = re.compile(r"\[[^\]\n]*\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _blocks(text):
    """(block id, body) for every generated block in a page, in page order."""
    return [(match.group("id"), match.group("body")) for match in publish.BLOCK.finditer(text)]


class CheckTest(unittest.TestCase):
    def test_a_clean_page_has_no_problems(self):
        text = "# Title\n\nA short page.\n\n| Size | Wait |\n|---|---:|\n| 8K | 24.5 s |\n"
        self.assertEqual(readable.check(text), [])

    def test_a_table_of_six_columns_is_a_problem(self):
        text = "| A | B | C | D | E | F |\n|---|---|---|---|---|---|\n| 1 | 2 | 3 | 4 | 5 | 6 |\n"
        problems = readable.check(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 1)
        self.assertIn("6 columns", problems[0].message)

    def test_a_table_of_five_columns_is_allowed(self):
        text = "| A | B | C | D | E |\n|---|---|---|---|---|\n| 1 | 2 | 3 | 4 | 5 |\n"
        self.assertEqual(readable.check(text), [])

    def test_a_banned_word_is_named_with_its_line(self):
        problems = readable.check("# Title\n\nThe wave took 10 s.\n")
        self.assertEqual([problem.line for problem in problems], [3])
        self.assertIn("'wave'", problems[0].message)

    def test_banned_words_are_found_in_any_case_and_in_the_plural(self):
        problems = readable.check("Waves and Arms and TTFT and Prefill\n")
        words = sorted(problem.message.split("'")[1] for problem in problems)
        self.assertEqual(words, ["Arms", "Prefill", "TTFT", "Waves"])

    def test_a_word_inside_a_banned_word_is_not_a_problem(self):
        self.assertEqual(readable.check("The warmth of the army was alarming.\n"), [])

    def test_a_banned_word_inside_a_fenced_block_is_not_read_as_prose(self):
        text = "Run this:\n\n```bash\npython3 bench/waves.py --cell arm\n```\n\nDone.\n"
        self.assertEqual(readable.check(text), [])

    def test_a_banned_word_inside_inline_code_is_not_read_as_prose(self):
        self.assertEqual(readable.check("The `wave` field is in the rows.\n"), [])

    def test_a_banned_word_in_a_link_target_is_not_read_as_prose(self):
        text = "See [the page](docs/many-waves-and-cells.md) for more.\n"
        self.assertEqual(readable.check(text), [])

    def test_a_file_name_in_src_is_not_read_as_prose(self):
        text = '<img src="charts/wave-light.svg" alt="a group of users">\n'
        self.assertEqual(readable.check(text), [])

    def test_alt_text_is_read_as_prose_because_a_person_reads_it(self):
        text = '<img src="charts/a-light.svg" alt="a wave of requests">\n'
        problems = readable.check(text)
        self.assertEqual([problem.line for problem in problems], [1])
        self.assertIn("'wave'", problems[0].message)

    def test_a_generated_marker_is_not_read_as_prose(self):
        text = "<!-- BEGIN GENERATED: speed-sweep box -->\n<!-- END GENERATED: speed-sweep box -->\n"
        self.assertEqual(readable.check(text), [])

    def test_a_fence_left_open_is_a_problem(self):
        text = "# Title\n\nRun this:\n\n```bash\npython3 bench/run.py\n"
        problems = readable.check(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 5)
        self.assertIn("unclosed code fence", problems[0].message)

    def test_a_fence_is_not_closed_by_a_longer_fence_with_a_word_after_it(self):
        text = "```\nhidden `wave`\n```python\nstill hidden `wave`\n```\n"
        self.assertEqual(readable.check(text), [])

    def test_a_fence_is_not_closed_by_a_shorter_or_other_fence(self):
        text = "````\nstill hidden `wave`\n```\nstill hidden `wave`\n~~~~\n````\n"
        self.assertEqual(readable.check(text), [])

    def test_closing_one_open_fence_does_not_hide_the_next_block(self):
        text = "```\nhidden\n```\n\nThe wave is visible here.\n"
        problems = readable.check(text)
        self.assertEqual([problem.line for problem in problems], [5])
        self.assertIn("'wave'", problems[0].message)

    def test_a_table_without_outer_pipes_is_still_a_table(self):
        text = "A | B | C | D | E | F\n---|---|---|---|---|---\n1 | 2 | 3 | 4 | 5 | 6\n"
        problems = readable.check(text)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].line, 1)
        self.assertIn("6 columns", problems[0].message)

    def test_a_narrow_table_without_outer_pipes_is_allowed(self):
        text = "A | B\n---|---\n1 | 2\n"
        self.assertEqual(readable.check(text), [])

    def test_a_line_with_a_pipe_that_is_not_under_a_separator_is_not_a_table(self):
        # Two cells of prose, not a table: no separator line under it.
        self.assertEqual(readable.check("six | seven\n"), [])

    def test_the_engine_names_and_status_words_are_banned(self):
        problems = readable.check("The ANE ran, then HTTP said no and Wilson agreed; see the JSONL.\n")
        words = sorted(problem.message.split("'")[1] for problem in problems)
        self.assertEqual(words, ["ANE", "HTTP", "JSONL", "Wilson"])

    def test_a_field_name_with_an_underscore_is_a_problem(self):
        problems = readable.check("The helper state at the start is in helper_ready_at_start.\n")
        self.assertEqual([problem.line for problem in problems], [1])
        self.assertIn("helper_ready_at_start", problems[0].message)
        self.assertIn("underscore", problems[0].message)

    def test_an_underscore_inside_code_or_a_link_is_not_prose(self):
        text = "Run `bench/quality_report.py` and see [it](bench/quality_report.py).\n"
        self.assertEqual(readable.check(text), [])

    def test_a_machine_label_in_prose_is_a_problem(self):
        problems = readable.check("The rows from m3-ultra-a are in the report.\n")
        self.assertEqual([problem.line for problem in problems], [1])
        self.assertIn("m3-ultra-a", problems[0].message)

    def test_a_machine_label_in_a_link_target_is_not_prose(self):
        text = "See [the report](reports/m3-ultra-a/speed.md) for the rows.\n"
        self.assertEqual(readable.check(text), [])

    def test_the_engine_name_for_compressed_prompt_memory_is_allowed_once_in_brackets(self):
        text = "# Page\n\nThe 4-bit prompt memory (Affine4) saves memory.\n\nIt is called Affine4 here.\n"
        problems = readable.check(text)
        self.assertEqual([problem.line for problem in problems], [5])
        self.assertIn("already named", problems[0].message)
        self.assertIn("4-bit prompt memory", problems[0].message)

    def test_the_engine_name_without_the_plain_words_is_a_problem(self):
        problems = readable.check("Affine8 stores the prompt memory in fewer bits.\n")
        self.assertEqual([problem.line for problem in problems], [1])
        self.assertIn("plain words", problems[0].message)

    def test_a_list_of_nine_bullets_is_a_problem(self):
        bullets = "".join(f"- bullet {number}\n" for number in range(1, 10))
        problems = readable.check("# Page\n\n" + bullets)
        self.assertEqual([problem.line for problem in problems], [3])
        self.assertIn("8 bullets", problems[0].message)

    def test_a_list_of_eight_bullets_is_allowed(self):
        bullets = "".join(f"- bullet {number}\n" for number in range(1, 9))
        self.assertEqual(readable.check("# Page\n\n" + bullets), [])

    def test_a_wrapped_line_does_not_end_a_list(self):
        bullets = "".join(f"- bullet {number}\n  and its second line\n" for number in range(1, 9))
        self.assertEqual(readable.check("# Page\n\n" + bullets), [])


class GeneratedBlocksTest(unittest.TestCase):
    """Every generated block in the reader pages follows the two rules a reader depends on."""

    def test_every_page_that_has_blocks_is_read(self):
        with_blocks = [page.name for page in PAGES if _blocks(page.read_text(encoding="utf-8"))]
        # The front door and the five topic pages, and nothing else.
        self.assertEqual(
            sorted(with_blocks),
            ["README.md", "answer-quality.md", "helper-setup.md", "many-users.md", "memory.md", "speed.md"],
        )

    def test_no_generated_block_breaks_a_rule(self):
        problems = []
        for page in PAGES:
            for block_id, body in _blocks(page.read_text(encoding="utf-8")):
                for problem in readable.check(body):
                    problems.append(f"{page.name} block {block_id!r} {problem}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_block_is_on_the_page_the_layout_names(self):
        found = {}
        for page in PAGES:
            for block_id, _ in _blocks(page.read_text(encoding="utf-8")):
                found.setdefault(block_id, set()).add(page.name)
        self.assertEqual(found["headline"], {"README.md"})
        self.assertEqual(found["speed m3-ultra-a"], {"speed.md"})
        self.assertEqual(found["speed m3-ultra-b"], {"speed.md"})
        self.assertEqual(found["speed-sweep m3-ultra-b"], {"speed.md"})
        self.assertEqual(found["many-users m3-ultra-b"], {"many-users.md"})
        self.assertEqual(found["kv-cache m3-ultra-a"], {"memory.md"})
        self.assertEqual(found["kv-cache m3-ultra-b"], {"memory.md"})
        self.assertEqual(found["quality m3-ultra-a"], {"answer-quality.md"})
        self.assertEqual(found["quality m3-ultra-b"], {"answer-quality.md"})
        self.assertEqual(found["helper-ready m3-ultra-a"], {"helper-setup.md"})
        self.assertEqual(found["helper-layers m3-ultra-a"], {"helper-setup.md"})

    def test_the_readme_carries_one_block_only(self):
        self.assertEqual([block_id for block_id, _ in _blocks((REPO_ROOT / "README.md").read_text(encoding="utf-8"))], ["headline"])

    def test_each_block_has_four_notes_or_fewer(self):
        for page in PAGES:
            for block_id, body in _blocks(page.read_text(encoding="utf-8")):
                notes = [line for line in body.splitlines() if line.startswith("- ")]
                self.assertLessEqual(len(notes), publish.MAX_NOTES, f"{page.name} block {block_id!r}")

    def test_a_block_shows_the_display_name_and_never_the_label(self):
        # A chart file is named after the results label, so only the attribute values are skipped;
        # everything a reader reads must use the display name.
        manifest = json.loads((REPO_ROOT / publish.MANIFEST).read_text(encoding="utf-8"))
        labels = [machine["label"] for machine in manifest["machines"]]
        names = [machine["display_name"] for machine in manifest["machines"]]
        attribute = re.compile(r"\b(?:src|srcset)\s*=\s*\"[^\"]*\"")
        for page in PAGES:
            for block_id, body in _blocks(page.read_text(encoding="utf-8")):
                prose = attribute.sub("", body)
                for label in labels:
                    self.assertNotIn(label, prose, f"{page.name} block {block_id!r} names the label {label!r}")
                self.assertTrue(any(name in prose for name in names), f"{page.name} block {block_id!r}")

    def test_a_wait_over_two_minutes_is_also_given_in_minutes(self):
        self.assertEqual(publish.duration(24.5), "24.5 s")
        self.assertEqual(publish.duration(638.1), "638.1 s (10.6 min)")

    def test_the_headline_block_links_a_chart_that_exists(self):
        body = dict(_blocks((REPO_ROOT / "README.md").read_text(encoding="utf-8")))["headline"]
        for name in re.findall(r'charts/[\w.-]+\.svg', body):
            self.assertTrue((REPO_ROOT / name).is_file(), f"{name} is not on disk")

    def test_every_block_with_a_chart_shows_its_picture(self):
        # A chart belongs beside the numbers it draws, so the block carries the picture itself.
        chart_of_block = {
            "speed": "-ttft-light.svg",
            "speed-sweep": "-ttft-sweep-light.svg",
            "kv-cache": "-kv-memory-light.svg",
            "quality": "-quality-light.svg",
            "helper-layers": "-helper-layers-light.svg",
            "many-users": "-many-users-light.svg",
            "headline": "headline-light.svg",
        }
        seen = []
        for page in PAGES:
            for block_id, body in _blocks(page.read_text(encoding="utf-8")):
                suffix = chart_of_block.get(block_id.split(" ")[0])
                if suffix is None:
                    continue
                self.assertIn("<picture>", body, f"{page.name} block {block_id!r} has no picture")
                self.assertRegex(body, re.escape(suffix) + r'"')
                self.assertRegex(body, re.escape(suffix.replace("-light", "-dark")))
                seen.append(block_id)
        self.assertEqual(len(seen), 10, seen)

    def test_every_chart_file_is_shown_on_a_page(self):
        names = {path.name for path in (REPO_ROOT / "charts").glob("*.svg")}
        shown = set()
        for page in PAGES:
            for match in re.findall(r"charts/[\w.-]+\.svg", page.read_text(encoding="utf-8")):
                shown.add(match.rsplit("/", 1)[-1])
        self.assertEqual(sorted(names - shown), [])


class ReaderPagesTextTest(unittest.TestCase):
    """The whole of every page a reader lands on, hand text and blocks together."""

    WHOLE = PAGES + [CONTRIBUTING]

    def test_every_page_a_reader_lands_on_is_checked(self):
        names = sorted(path.name for path in self.WHOLE)
        self.assertEqual(
            names,
            [
                "CONTRIBUTING.md",
                "README.md",
                "answer-quality.md",
                "files.md",
                "helper-setup.md",
                "many-users.md",
                "memory.md",
                "method.md",
                "run-it.md",
                "speed.md",
            ],
        )

    def test_no_page_breaks_a_rule(self):
        problems = []
        for path in self.WHOLE:
            for problem in readable.check(path.read_text(encoding="utf-8")):
                problems.append(f"{path.relative_to(REPO_ROOT)} {problem}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_front_door_is_short_enough_to_read(self):
        lines = (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), MAX_README_LINES, f"README.md is {len(lines)} lines")


class PageLinkTest(unittest.TestCase):
    """Every relative link on a page points at a file or folder that is there."""

    def test_every_relative_link_resolves(self):
        missing = []
        for page in PAGES:
            for match in LINK.finditer(page.read_text(encoding="utf-8")):
                target = match.group("target").split("#")[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not (page.parent / target).exists():
                    missing.append(f"{page.relative_to(REPO_ROOT)} -> {target}")
        self.assertEqual(missing, [], "\n".join(missing))


class ChartTextTest(unittest.TestCase):
    """A chart says the same plain things a page does, and its words stay inside the picture."""

    CHARTS = sorted((REPO_ROOT / "charts").glob("*.svg"))

    def _texts(self, path):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        return [node for node in root.iter(f"{SVG_NS}text")]

    def _words(self, path):
        """Every word inside the picture: its title, its subtitle and its labels.

        The title and the subtitle are drawn as text, and the image's own title is read out by a
        screen reader, so all of it is text a person meets.
        """
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        return [node.text or "" for node in root.iter() if node.tag in (f"{SVG_NS}text", f"{SVG_NS}title")]

    def test_there_is_a_chart_to_check(self):
        self.assertGreaterEqual(len(self.CHARTS), 20)
        self.assertIn(REPO_ROOT / "charts/headline-light.svg", self.CHARTS)

    def test_no_chart_uses_a_hard_word(self):
        problems = []
        for path in self.CHARTS:
            words = self._words(path)
            for problem in readable.check("\n".join(words)):
                problems.append(f"{path.name} {problem} in: {words[problem.line - 1]}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_no_chart_asks_the_reader_to_hover(self):
        # A chart on a page is a still image: a hover tip is not there for the reader.
        problems = [
            f"{path.name}: {word!r}"
            for path in self.CHARTS
            for word in self._words(path)
            if "hover" in word.lower()
        ]
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_bar_chart_names_its_axis_and_unit(self):
        for name in ("m3-ultra-a-ttft", "m3-ultra-a-kv-memory", "m3-ultra-a-helper-layers", "m3-ultra-a-quality"):
            words = self._words(REPO_ROOT / f"charts/{name}-light.svg")
            self.assertTrue(any("(" in word and ")" in word for word in words), f"{name} has no unit")
            self.assertTrue(
                any(word.startswith("Wait for the first word") or word.startswith("Peak memory")
                    or word.startswith("Share of answers") for word in words),
                f"{name} has no axis name",
            )

    def test_no_chart_text_runs_off_the_picture(self):
        problems = []
        for path in self.CHARTS:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
            width = float(root.get("width"))
            for node in root.iter(f"{SVG_NS}text"):
                if node.get("transform"):
                    continue  # turned on its side: its width is the height of a line
                size = float(node.get("font-size"))
                x = float(node.get("x"))
                wide = len(node.text or "") * size * 0.6
                anchor = node.get("text-anchor") or "start"
                left = x - wide / 2 if anchor == "middle" else (x - wide if anchor == "end" else x)
                if left < 0 or left + wide > width:
                    problems.append(f"{path.name}: {node.text!r} reaches {left:.0f} to {left + wide:.0f} of {width:.0f}")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
