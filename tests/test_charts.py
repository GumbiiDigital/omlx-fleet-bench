"""Tests for the SVG writer, the chart forms, labels and statistics."""

import unittest
import xml.etree.ElementTree as ET

from bench import charts, labels, stats
from bench.svg import DARK, LIGHT, THEMES, Canvas, num, text_width

SVG_NS = "{http://www.w3.org/2000/svg}"


def _texts(svg: str):
    return [node.text for node in ET.fromstring(svg).iter(f"{SVG_NS}text")]


def _bar_panels():
    return [
        charts.BarPanel(
            title="8K prompt",
            rows=[
                charts.BarRow("GPU only", 24.5, "24.5 s", "blue", "baseline"),
                charts.BarRow("+ Spark helper", 8.6, "8.59 s", "aqua", "2.8× faster"),
            ],
        ),
        charts.BarPanel(
            title="32K prompt",
            rows=[
                charts.BarRow("GPU only", 110.0, "110 s", "blue", "baseline"),
                charts.BarRow("+ Spark helper", 35.1, "35.1 s", "aqua", "3.1× faster"),
            ],
        ),
    ]


class SvgTest(unittest.TestCase):
    def test_num_is_short_and_stable(self):
        self.assertEqual(num(12.0), "12")
        self.assertEqual(num(12.345), "12.35")
        self.assertEqual(num(-0.001), "0")

    def test_bold_text_is_estimated_wider(self):
        self.assertGreater(text_width("98.0%", 12, bold=True), text_width("98.0%", 12))

    def test_canvas_escapes_text_and_label(self):
        canvas = Canvas(100, 50, LIGHT, label='a "quoted" <label>')
        canvas.text(0, 10, "x < y & z")
        root = ET.fromstring(canvas.render())
        self.assertEqual(root.get("aria-label"), 'a "quoted" <label>')
        self.assertEqual(root.find(f"{SVG_NS}text").text, "x < y & z")

    def test_themes_define_the_same_series(self):
        self.assertEqual(set(LIGHT.series), set(DARK.series))
        self.assertEqual(set(THEMES), {"light", "dark"})


class BarPanelsTest(unittest.TestCase):
    def setUp(self):
        self.caption = charts.Caption("Time to first token", ["model · machine"], ["a footnote"])

    def test_every_label_value_and_note_is_drawn(self):
        texts = _texts(charts.bar_panels(self.caption, _bar_panels(), LIGHT))
        for expected in ("Time to first token", "8K prompt", "+ Spark helper", "8.59 s", "3.1× faster", "a footnote"):
            self.assertIn(expected, texts)

    def test_longest_bar_in_each_panel_fills_the_same_track(self):
        root = ET.fromstring(charts.bar_panels(self.caption, _bar_panels(), LIGHT))
        bars = [node for node in root.iter(f"{SVG_NS}path")]
        self.assertEqual(len(bars), 4)

        def width(path):
            x0 = float(path.get("d").split()[0][1:].split(",")[0])
            return float(path.get("d").split(" V")[0].rsplit(" ", 1)[1].split(",")[0]) - x0

        self.assertAlmostEqual(width(bars[0]), width(bars[2]), places=1)
        self.assertLess(width(bars[1]), width(bars[0]))

    def test_marks_use_the_theme_colour_and_text_does_not(self):
        root = ET.fromstring(charts.bar_panels(self.caption, _bar_panels(), DARK))
        fills = {node.get("fill") for node in root.iter(f"{SVG_NS}path")}
        self.assertEqual(fills, {DARK.series["blue"], DARK.series["aqua"]})
        text_fills = {node.get("fill") for node in root.iter(f"{SVG_NS}text")}
        self.assertTrue(text_fills.isdisjoint(DARK.series.values()))

    def test_same_input_gives_the_same_bytes(self):
        first = charts.bar_panels(self.caption, _bar_panels(), LIGHT)
        self.assertEqual(first, charts.bar_panels(self.caption, _bar_panels(), LIGHT))

    def test_no_panels_is_an_error(self):
        with self.assertRaises(ValueError):
            charts.bar_panels(self.caption, [], LIGHT)


class IntervalPanelsTest(unittest.TestCase):
    def _svg(self, **kwargs):
        panels = [
            charts.IntervalPanel(
                title="GSM8K · 200 questions",
                rows=[
                    charts.IntervalRow("GPU only", 97.5, 94.3, 98.9, "97.5%", "blue", "195/200"),
                    charts.IntervalRow("Affine4 KV", 98.0, 95.0, 99.2, "98.0%", "magenta", "196/200"),
                ],
            )
        ]
        options = dict(axis_min=85.0, axis_max=100.0, ticks=[85, 90, 95, 100], tick_suffix="%")
        options.update(kwargs)
        return charts.interval_panels(charts.Caption("Accuracy"), panels, LIGHT, **options)

    def test_dots_sit_inside_their_intervals_in_value_order(self):
        root = ET.fromstring(self._svg())
        dots = [float(node.get("cx")) for node in root.iter(f"{SVG_NS}circle")]
        self.assertEqual(len(dots), 2)
        self.assertLess(dots[0], dots[1])
        whiskers = [n for n in root.iter(f"{SVG_NS}line") if n.get("stroke-width") == "2"]
        for dot, whisker in zip(dots, whiskers):
            self.assertLess(float(whisker.get("x1")), dot)
            self.assertGreater(float(whisker.get("x2")), dot)

    def test_ticks_and_values_are_drawn(self):
        texts = _texts(self._svg())
        for expected in ("85%", "100%", "97.5%", "196/200"):
            self.assertIn(expected, texts)

    def test_bad_axis_is_an_error(self):
        with self.assertRaises(ValueError):
            self._svg(axis_min=100.0, axis_max=85.0)


class LabelsTest(unittest.TestCase):
    def test_known_variants_keep_the_fixed_order(self):
        self.assertEqual(
            labels.ordered_variants(["spark", "gpu", "ane", "affine8", "affine4"]),
            ["gpu", "affine4", "affine8", "ane", "spark"],
        )

    def test_unknown_variants_come_last_and_get_spare_colours(self):
        self.assertEqual(labels.ordered_variants(["zeta", "gpu", "alpha"]), ["gpu", "alpha", "zeta"])
        series = labels.variant_series(["gpu", "alpha", "zeta"])
        self.assertEqual(series, {"gpu": "blue", "alpha": "green", "zeta": "red"})
        self.assertEqual(labels.variant_label("alpha"), "alpha")

    def test_running_out_of_colours_is_an_error(self):
        with self.assertRaises(ValueError):
            labels.variant_series(["a", "b", "c"])

    def test_every_series_name_exists_in_both_themes(self):
        for slot in list(labels.VARIANT_SERIES.values()) + labels.SPARE_SERIES:
            self.assertIn(slot, LIGHT.series)
            self.assertIn(slot, DARK.series)

    def test_size_label(self):
        self.assertEqual(labels.size_label(8192), "8K")
        self.assertEqual(labels.size_label(131072), "128K")
        self.assertEqual(labels.size_label(1000), "1,000")


class StatsTest(unittest.TestCase):
    def test_spread(self):
        self.assertEqual(stats.spread([5.0]), 0.0)
        self.assertEqual(stats.spread([0.0, 0.0]), 0.0)
        self.assertAlmostEqual(stats.spread([90.0, 100.0, 110.0]), 0.2)

    def test_wilson_interval_matches_known_values(self):
        low, high = stats.wilson_interval(195, 200)
        self.assertAlmostEqual(low, 0.9428, places=3)
        self.assertAlmostEqual(high, 0.9893, places=3)

    def test_wilson_interval_stays_inside_zero_and_one(self):
        low, high = stats.wilson_interval(6, 6)
        self.assertGreater(low, 0.5)
        self.assertEqual(high, 1.0)
        low, high = stats.wilson_interval(0, 6)
        self.assertAlmostEqual(low, 0.0)
        self.assertLess(high, 0.5)

    def test_wilson_interval_rejects_bad_counts(self):
        with self.assertRaises(ValueError):
            stats.wilson_interval(1, 0)
        with self.assertRaises(ValueError):
            stats.wilson_interval(7, 6)


if __name__ == "__main__":
    unittest.main()
