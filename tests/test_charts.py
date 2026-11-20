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


class LinePanelTest(unittest.TestCase):
    def _panel(self) -> charts.LinePanel:
        return charts.LinePanel(
            title="Time to first token by prompt size",
            x_min=1024,
            x_max=131072,
            y_min=1.5,
            y_max=140.0,
            x_ticks=[(1024, "1K"), (8192, "8K"), (16384, "16K"), (131072, "128K")],
            y_ticks=[(2.0, "2 s"), (10.0, "10 s"), (100.0, "100 s")],
            series=[
                charts.LineSeries(
                    "GPU only",
                    "blue",
                    [
                        charts.LinePoint(1024, 1.7, "1K", "1.7 s"),
                        charts.LinePoint(8192, 8.7, "8K", "8.7 s"),
                        charts.LinePoint(16384, 16.6, "16K", "17 s"),
                        charts.LinePoint(131072, 137.1, "128K", "137 s"),
                    ],
                ),
                charts.LineSeries(
                    "+ Spark helper",
                    "aqua",
                    [
                        charts.LinePoint(1024, 1.5, "1K", "1.5 s"),
                        charts.LinePoint(131072, 58.4, "128K", "58.4 s"),
                    ],
                ),
            ],
        )

    def setUp(self):
        self.caption = charts.Caption("Time to first token by prompt size", ["model · machine"], ["both axes are log"])

    def _svg(self, panel=None, theme=LIGHT):
        return charts.line_panel(self.caption, panel or self._panel(), theme)

    def test_series_labels_ticks_and_footnote_are_drawn(self):
        texts = _texts(self._svg())
        for expected in ("GPU only", "+ Spark helper", "1K", "128K", "2 s", "100 s", "both axes are log"):
            self.assertIn(expected, texts)

    def test_every_point_carries_its_value_as_drawn_text(self):
        # A chart is read as a still image, so the value has to be in the picture, not in a hover tip.
        svg = self._svg()
        self.assertIn("8.7 s", _texts(svg))
        self.assertIn("1.5 s", _texts(svg))
        titles = [node.text for node in ET.fromstring(svg).iter(f"{SVG_NS}title")]
        self.assertIn("Time to first token by prompt size · GPU only · 8K: 8.7 s", titles)

    def test_both_axes_are_logarithmic(self):
        root = ET.fromstring(self._svg())
        dots = [(float(n.get("cx")), float(n.get("cy"))) for n in root.iter(f"{SVG_NS}circle")]
        self.assertEqual(len(dots), 6)
        (x_1k, y_1k), (x_8k, y_8k), (x_16k, _), (x_128k, _) = dots[0:4]
        # Three octaves (1K to 8K) must be three times one octave (8K to 16K) on x.
        self.assertAlmostEqual(x_8k - x_1k, 3 * (x_16k - x_8k), places=1)
        # The axis is shared, so both lines end on the same x.
        self.assertAlmostEqual(x_128k, dots[5][0], places=1)
        # A longer wait sits higher on the chart, as on any axis.
        self.assertLess(y_8k, y_1k)

    def test_each_series_uses_its_theme_colour(self):
        root = ET.fromstring(self._svg(theme=DARK))
        strokes = {node.get("stroke") for node in root.iter(f"{SVG_NS}line")}
        self.assertIn(DARK.series["blue"], strokes)
        self.assertIn(DARK.series["aqua"], strokes)

    def test_same_input_gives_the_same_bytes(self):
        self.assertEqual(self._svg(), self._svg())

    def test_no_series_or_a_flat_axis_is_an_error(self):
        with self.assertRaises(ValueError):
            charts.line_panel(self.caption, charts.LinePanel("t", 1.0, 10.0, 1.0, 10.0, [], [], []), LIGHT)
        flat = self._panel()
        with self.assertRaises(ValueError):
            charts.line_panel(
                self.caption,
                charts.LinePanel(flat.title, 0.0, flat.x_max, flat.y_min, flat.y_max, flat.x_ticks, flat.y_ticks, flat.series),
                LIGHT,
            )


class LinePanelsTest(unittest.TestCase):
    """Several line charts in one figure, on one shared pair of ranges."""

    def setUp(self):
        self.caption = charts.Caption("Wave time by number of users", ["model · machine"], ["a footnote"])

    @staticmethod
    def _panel(title, alone, helped):
        """One panel per prompt size: two arms, four user counts, the same ranges on every panel."""

        def points(values):
            return [
                charts.LinePoint(users, value, f"{users} users", f"{value:.1f} s")
                for users, value in zip((1, 2, 4, 8), values)
            ]

        return charts.LinePanel(
            title=title,
            x_min=1,
            x_max=8,
            y_min=7.0,
            y_max=330.0,
            x_ticks=[(1, "1"), (2, "2"), (4, "4"), (8, "8")],
            y_ticks=[(10.0, "10 s"), (100.0, "100 s")],
            series=[
                charts.LineSeries("Mac alone", "blue", points(alone)),
                charts.LineSeries("With helper", "aqua", points(helped)),
            ],
        )

    def _panels(self):
        return [
            self._panel("4K prompt", (7.9, 19.2, 33.2, 65.5), (7.2, 14.2, 23.1, 42.0)),
            self._panel("32K prompt", (38.7, 79.2, 161.3, 324.7), (20.4, 38.7, 75.6, 149.5)),
        ]

    def _svg(self, panels=None, theme=LIGHT):
        return charts.line_panels(self.caption, panels or self._panels(), theme)

    def test_every_panel_title_and_one_legend_are_drawn(self):
        texts = _texts(self._svg())
        self.assertIn("4K prompt", texts)
        self.assertIn("32K prompt", texts)
        # The legend is one row for the whole figure, so each arm is named once.
        self.assertEqual(texts.count("Mac alone"), 1)
        self.assertEqual(texts.count("With helper"), 1)
        self.assertIn("a footnote", texts)

    def test_every_point_carries_its_value_as_drawn_text(self):
        svg = self._svg()
        self.assertIn("42.0 s", _texts(svg))
        self.assertIn("324.7 s", _texts(svg))
        titles = [node.text for node in ET.fromstring(svg).iter(f"{SVG_NS}title")]
        self.assertIn("4K prompt · With helper · 8 users: 42.0 s", titles)
        self.assertIn("32K prompt · Mac alone · 8 users: 324.7 s", titles)

    def test_the_panels_share_one_scale(self):
        root = ET.fromstring(self._svg())
        dots = [(float(node.get("cx")), float(node.get("cy"))) for node in root.iter(f"{SVG_NS}circle")]
        self.assertEqual(len(dots), 16)
        # 4K at 8 users with the helper (42.0 s) against 32K at 8 users on the Mac alone (324.7 s):
        # the shared scale puts the longer wave higher up, in either panel.
        first_panel, second_panel = dots[:8], dots[8:]
        self.assertLess(second_panel[7][1], first_panel[7][1])

    def test_each_arm_uses_its_theme_colour_in_every_panel(self):
        root = ET.fromstring(self._svg(theme=DARK))
        strokes = {node.get("stroke") for node in root.iter(f"{SVG_NS}line")}
        self.assertIn(DARK.series["blue"], strokes)
        self.assertIn(DARK.series["aqua"], strokes)

    def test_same_input_gives_the_same_bytes(self):
        self.assertEqual(self._svg(), self._svg())

    def test_no_panels_is_an_error(self):
        with self.assertRaises(ValueError):
            charts.line_panels(self.caption, [], LIGHT)

    def test_a_panel_with_no_series_is_an_error(self):
        with self.assertRaises(ValueError):
            charts.line_panels(self.caption, [charts.LinePanel("t", 1.0, 10.0, 1.0, 10.0, [], [], [])], LIGHT)


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

    def test_arms_run_mac_alone_then_helper_and_keep_their_colours(self):
        self.assertEqual(labels.ordered_arms(["helper", "mac-alone"]), ["mac-alone", "helper"])
        self.assertEqual([labels.arm_label(arm) for arm in ("mac-alone", "helper")], ["Mac alone", "Mac + Spark"])
        for colour in labels.arm_series(["mac-alone", "helper"]).values():
            self.assertIn(colour, LIGHT.series)
            self.assertIn(colour, DARK.series)

    def test_an_arm_without_a_colour_is_an_error(self):
        with self.assertRaises(ValueError):
            labels.arm_series(["gyro"])

    def test_a_layer_setting_is_named_by_what_was_asked_for(self):
        self.assertEqual(labels.setting_label("mac-alone"), "Mac alone")
        self.assertEqual(labels.setting_label("automatic"), "Automatic")
        self.assertEqual(labels.setting_label("layers-32"), "32 layers")
        self.assertEqual(labels.setting_label("something-else"), "something-else")

    def test_settings_are_ordered_mac_alone_then_automatic_then_layer_counts(self):
        self.assertEqual(
            labels.ordered_settings(["layers-63", "mac-alone", "layers-32", "automatic", "layers-49"]),
            ["mac-alone", "automatic", "layers-32", "layers-49", "layers-63"],
        )

    def test_a_setting_keeps_one_colour_and_runs_out_loudly(self):
        series = labels.setting_series(["layers-49", "mac-alone", "automatic"])
        self.assertEqual(series["mac-alone"], "blue")
        self.assertEqual(len(set(series.values())), 3)
        with self.assertRaises(ValueError):
            labels.setting_series([f"layers-{count}" for count in range(20)])


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
