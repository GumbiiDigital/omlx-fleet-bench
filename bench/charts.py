"""Three chart forms, drawn as SVG: bar panels (a magnitude), interval panels (a rate
with its uncertainty) and a line panel (a value that runs across decades).

This module knows nothing about benchmarks. Callers turn their rows into `BarPanel`,
`IntervalPanel` or `LinePanel` values and pick a theme; the same input gives the same bytes.

Design rules the layout follows: thin bars from one baseline with the value at the tip,
one scale per panel, text in ink colours (never the series colour), a tooltip on every
mark, and a width that stays readable at README column width.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from bench.svg import Canvas, Theme, text_width

WIDTH = 840
PAD = 24
PANEL_GAP = 32
ROW_PITCH = 26
BAR_HEIGHT = 14
PANEL_TITLE_HEIGHT = 26
AXIS_LABEL_HEIGHT = 20
PANEL_ROW_GAP = 22
LINE_PLOT_HEIGHT = 300
LEGEND_ROW_HEIGHT = 18

TITLE_SIZE = 16
SUBTITLE_SIZE = 12
PANEL_TITLE_SIZE = 13
LABEL_SIZE = 12
VALUE_SIZE = 12
NOTE_SIZE = 11
FOOTNOTE_SIZE = 11
LINE_HEIGHT = 17


@dataclass(frozen=True)
class BarRow:
    label: str
    value: float
    value_text: str
    series: str
    note: str = ""


@dataclass(frozen=True)
class BarPanel:
    title: str
    rows: Sequence[BarRow]


@dataclass(frozen=True)
class IntervalRow:
    label: str
    value: float
    low: float
    high: float
    value_text: str
    series: str
    note: str = ""


@dataclass(frozen=True)
class IntervalPanel:
    title: str
    rows: Sequence[IntervalRow]


@dataclass(frozen=True)
class LinePoint:
    """One measured point. `x_text` and `y_text` are its labels; they go in the tooltip."""

    x: float
    y: float
    x_text: str
    y_text: str


@dataclass(frozen=True)
class LineSeries:
    label: str
    series: str
    points: Sequence[LinePoint]


@dataclass(frozen=True)
class LinePanel:
    """A value against another on log axes, one line per series.

    `x_ticks` and `y_ticks` are (value, label) pairs, so the caller owns the wording and
    the axis spans exactly the range it states.
    """

    title: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    x_ticks: Sequence[Tuple[float, str]]
    y_ticks: Sequence[Tuple[float, str]]
    series: Sequence[LineSeries]


@dataclass(frozen=True)
class Caption:
    """The words around a figure. `label` is the accessible name of the image."""

    title: str
    subtitle: Sequence[str] = ()
    footnotes: Sequence[str] = ()

    @property
    def label(self) -> str:
        return " ".join([self.title, *self.subtitle])


def _header_height(caption: Caption) -> float:
    return PAD + TITLE_SIZE + 6 + len(caption.subtitle) * LINE_HEIGHT + 12


def _footer_height(caption: Caption) -> float:
    if not caption.footnotes:
        return PAD - 8
    return 6 + len(caption.footnotes) * (FOOTNOTE_SIZE + 5) + PAD - 8


def _grid(count: int, columns: int, panel_height: float, top: float) -> Tuple[List[Tuple[float, float]], float, float]:
    """Top-left corner of each panel, the panel width, and the y where the grid ends."""
    columns = max(1, min(columns, count))
    panel_width = (WIDTH - 2 * PAD - (columns - 1) * PANEL_GAP) / columns
    origins = []
    for index in range(count):
        col, row = index % columns, index // columns
        origins.append((PAD + col * (panel_width + PANEL_GAP), top + row * (panel_height + PANEL_ROW_GAP)))
    grid_rows = (count + columns - 1) // columns
    bottom = top + grid_rows * panel_height + (grid_rows - 1) * PANEL_ROW_GAP
    return origins, panel_width, bottom


def _open(caption: Caption, theme: Theme, height: float) -> Canvas:
    canvas = Canvas(WIDTH, height, theme, label=caption.label)
    canvas.rect(0.5, 0.5, WIDTH - 1, height - 1, theme.surface, radius=8, stroke=theme.border)
    y = PAD + TITLE_SIZE
    canvas.text(PAD, y, caption.title, size=TITLE_SIZE, weight=600)
    for line in caption.subtitle:
        y += LINE_HEIGHT
        canvas.text(PAD, y, line, size=SUBTITLE_SIZE, fill=theme.secondary)
    return canvas


def _close(canvas: Canvas, caption: Caption, grid_bottom: float) -> str:
    y = grid_bottom + 6
    for line in caption.footnotes:
        y += FOOTNOTE_SIZE + 5
        canvas.text(PAD, y, line, size=FOOTNOTE_SIZE, fill=canvas.theme.muted)
    return canvas.render()


def _label_width(labels: Sequence[str]) -> float:
    return max([text_width(label, LABEL_SIZE) for label in labels] + [60.0]) + 14


def _value_width(rows: Sequence) -> float:
    widest = 0.0
    for row in rows:
        width = text_width(row.value_text, VALUE_SIZE, bold=True)
        if row.note:
            width += 8 + text_width(row.note, NOTE_SIZE)
        widest = max(widest, width)
    return widest + 14


def _value_label(canvas: Canvas, x: float, baseline: float, row) -> None:
    canvas.text(x, baseline, row.value_text, size=VALUE_SIZE, weight=600)
    if row.note:
        canvas.text(
            x + text_width(row.value_text, VALUE_SIZE, bold=True) + 8,
            baseline,
            row.note,
            size=NOTE_SIZE,
            fill=canvas.theme.muted,
        )


def bar_panels(caption: Caption, panels: Sequence[BarPanel], theme: Theme, *, columns: int = 2) -> str:
    """Horizontal bars, one panel per group. Each panel has its own scale, so compare
    bars inside a panel; the printed values carry the comparison across panels."""
    if not panels:
        raise ValueError("no panels")
    all_rows = [row for panel in panels for row in panel.rows]
    label_w = _label_width([row.label for row in all_rows])
    value_w = _value_width(all_rows)
    panel_height = PANEL_TITLE_HEIGHT + max(len(panel.rows) for panel in panels) * ROW_PITCH
    top = _header_height(caption)
    origins, panel_width, bottom = _grid(len(panels), columns, panel_height, top)
    track = panel_width - label_w - value_w
    if track < 40:
        raise ValueError("labels leave no room for the bars; use fewer columns")

    canvas = _open(caption, theme, bottom + _footer_height(caption))
    for panel, (px, py) in zip(panels, origins):
        canvas.text(px, py + PANEL_TITLE_SIZE, panel.title, size=PANEL_TITLE_SIZE, weight=600)
        rows_top = py + PANEL_TITLE_HEIGHT
        x0 = px + label_w
        scale = max((row.value for row in panel.rows), default=0.0) or 1.0
        for index, row in enumerate(panel.rows):
            y = rows_top + index * ROW_PITCH
            baseline = y + BAR_HEIGHT - 2.5
            canvas.text(px, baseline, row.label, size=LABEL_SIZE, fill=theme.secondary)
            width = max(row.value, 0.0) / scale * track
            canvas.bar(
                x0,
                y,
                width,
                BAR_HEIGHT,
                theme.series[row.series],
                tooltip=f"{panel.title} · {row.label}: {row.value_text} {row.note}".strip(),
            )
            _value_label(canvas, x0 + width + 8, baseline, row)
        canvas.line(x0, rows_top - 4, x0, rows_top + len(panel.rows) * ROW_PITCH - 8, theme.axis)
    return _close(canvas, caption, bottom)


def interval_panels(
    caption: Caption,
    panels: Sequence[IntervalPanel],
    theme: Theme,
    *,
    axis_min: float,
    axis_max: float,
    ticks: Sequence[float],
    tick_suffix: str = "",
    columns: int = 2,
) -> str:
    """A dot for the measured rate and a line for its interval, one row per setting.

    Every panel shares the same axis, so overlap between rows and panels can be read
    directly. The axis does not start at zero: position, not length, carries the value.
    """
    if not panels:
        raise ValueError("no panels")
    if axis_max <= axis_min:
        raise ValueError("axis_max must be above axis_min")
    all_rows = [row for panel in panels for row in panel.rows]
    label_w = _label_width([row.label for row in all_rows])
    value_w = _value_width(all_rows) + 6
    panel_height = PANEL_TITLE_HEIGHT + max(len(panel.rows) for panel in panels) * ROW_PITCH + AXIS_LABEL_HEIGHT
    top = _header_height(caption)
    origins, panel_width, bottom = _grid(len(panels), columns, panel_height, top)
    track = panel_width - label_w - value_w
    if track < 60:
        raise ValueError("labels leave no room for the plot; use fewer columns")

    def x_of(origin: float, value: float) -> float:
        clamped = min(max(value, axis_min), axis_max)
        return origin + (clamped - axis_min) / (axis_max - axis_min) * track

    canvas = _open(caption, theme, bottom + _footer_height(caption))
    for panel, (px, py) in zip(panels, origins):
        canvas.text(px, py + PANEL_TITLE_SIZE, panel.title, size=PANEL_TITLE_SIZE, weight=600)
        rows_top = py + PANEL_TITLE_HEIGHT
        rows_bottom = rows_top + len(panel.rows) * ROW_PITCH - 6
        x0 = px + label_w
        for tick in ticks:
            x = x_of(x0, tick)
            canvas.line(x, rows_top - 4, x, rows_bottom, theme.grid)
            canvas.text(
                x, rows_bottom + 14, f"{tick:g}{tick_suffix}", size=NOTE_SIZE, fill=theme.muted, anchor="middle"
            )
        for index, row in enumerate(panel.rows):
            y = rows_top + index * ROW_PITCH + BAR_HEIGHT / 2
            baseline = y + 4
            colour = theme.series[row.series]
            canvas.text(px, baseline, row.label, size=LABEL_SIZE, fill=theme.secondary)
            canvas.line(x_of(x0, row.low), y, x_of(x0, row.high), y, colour, width=2, round_cap=True)
            canvas.dot(
                x_of(x0, row.value),
                y,
                5,
                colour,
                ring=theme.surface,
                tooltip=(
                    f"{panel.title} · {row.label}: {row.value_text} {row.note} "
                    f"(interval {row.low:.1f} to {row.high:.1f}{tick_suffix})"
                ),
            )
            _value_label(canvas, x0 + track + 14, baseline, row)
    return _close(canvas, caption, bottom)


def _legend(canvas: Canvas, panel: LinePanel, y: float) -> None:
    """Series names in one row above the plot, each after a swatch in its own colour."""
    x = PAD
    for series in panel.series:
        canvas.line(x, y - 4, x + 14, y - 4, canvas.theme.series[series.series], width=2, round_cap=True)
        canvas.text(x + 20, y, series.label, size=NOTE_SIZE, fill=canvas.theme.secondary)
        x += 20 + text_width(series.label, NOTE_SIZE) + 24


def line_panel(caption: Caption, panel: LinePanel, theme: Theme) -> str:
    """One line per series, against a value that runs across decades, on log axes.

    Position carries the value on both axes, so a straight line means a constant growth
    rate. Every point gets its value in a tooltip rather than a label: on a line, labels
    collide where two series meet.
    """
    if not panel.series:
        raise ValueError("no series")
    if min(panel.x_min, panel.y_min) <= 0 or panel.x_max <= panel.x_min or panel.y_max <= panel.y_min:
        raise ValueError("log axes need a positive range")
    points = [point for series in panel.series for point in series.points]
    if not points:
        raise ValueError("no points")

    def log_span(low: float, high: float):
        floor, span = math.log10(low), math.log10(high) - math.log10(low)
        return lambda value: (math.log10(min(max(value, low), high)) - floor) / span

    across, down = log_span(panel.x_min, panel.x_max), log_span(panel.y_min, panel.y_max)
    gutter = max([text_width(label, NOTE_SIZE) for _, label in panel.y_ticks] + [24.0]) + 12
    left, right = PAD + gutter, WIDTH - PAD - 24
    top = _header_height(caption) + LEGEND_ROW_HEIGHT + 4
    bottom = top + LINE_PLOT_HEIGHT

    def x_of(value: float) -> float:
        return left + across(value) * (right - left)

    def y_of(value: float) -> float:
        return bottom - down(value) * LINE_PLOT_HEIGHT

    canvas = _open(caption, theme, bottom + LEGEND_ROW_HEIGHT + _footer_height(caption))
    _legend(canvas, panel, top - LEGEND_ROW_HEIGHT + 4)
    for value, label in panel.y_ticks:
        y = y_of(value)
        canvas.line(left, y, right, y, theme.grid)
        canvas.text(left - 8, y + 4, label, size=NOTE_SIZE, fill=theme.muted, anchor="end")
    for value, label in panel.x_ticks:
        x = x_of(value)
        canvas.line(x, top, x, bottom, theme.grid)
        canvas.text(x, bottom + 14, label, size=NOTE_SIZE, fill=theme.muted, anchor="middle")
    canvas.line(left, top, left, bottom, theme.axis)
    canvas.line(left, bottom, right, bottom, theme.axis)

    for series in panel.series:
        colour = theme.series[series.series]
        placed = [(x_of(point.x), y_of(point.y)) for point in series.points]
        for (x1, y1), (x2, y2) in zip(placed, placed[1:]):
            canvas.line(x1, y1, x2, y2, colour, width=2, round_cap=True)
        for point, (x, y) in zip(series.points, placed):
            canvas.dot(
                x,
                y,
                4,
                colour,
                ring=theme.surface,
                tooltip=f"{panel.title} · {series.label} · {point.x_text}: {point.y_text}",
            )
    return _close(canvas, caption, bottom + LEGEND_ROW_HEIGHT - 6)
