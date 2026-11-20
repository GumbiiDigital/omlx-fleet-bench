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
# A panel that shares the picture with others gets a shorter plot, so two fit across the width.
PANEL_PLOT_HEIGHT = 210

TITLE_SIZE = 16
SUBTITLE_SIZE = 12
# Caption text is wrapped to this width. The glyph estimate here is generous, so the wrap keeps
# a margin under the picture edge rather than running a word off it.
CAPTION_WIDTH = (WIDTH - 2 * PAD) * 0.9
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
    the axis spans exactly the range it states. `x_label` and `y_label` name the two axes;
    they carry no numbers, so they can be left empty.
    """

    title: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    x_ticks: Sequence[Tuple[float, str]]
    y_ticks: Sequence[Tuple[float, str]]
    series: Sequence[LineSeries]
    x_label: str = ""
    y_label: str = ""


@dataclass(frozen=True)
class Caption:
    """The words around a figure. `label` is the accessible name of the image."""

    title: str
    subtitle: Sequence[str] = ()
    footnotes: Sequence[str] = ()

    @property
    def label(self) -> str:
        return " ".join([self.title, *self.subtitle])


def _wrap(text: str, size: float, width: float) -> List[str]:
    """Break a line of words to fit `width`, so no caption runs off the picture."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and text_width(candidate, size) > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def _subtitle_lines(caption: Caption) -> List[str]:
    return [line for entry in caption.subtitle for line in _wrap(entry, SUBTITLE_SIZE, CAPTION_WIDTH)]


def _footnote_lines(caption: Caption) -> List[str]:
    return [line for entry in caption.footnotes for line in _wrap(entry, FOOTNOTE_SIZE, CAPTION_WIDTH)]


def _header_height(caption: Caption) -> float:
    return PAD + TITLE_SIZE + 6 + len(_subtitle_lines(caption)) * LINE_HEIGHT + 12


def _footer_height(caption: Caption) -> float:
    if not caption.footnotes:
        return PAD - 8
    return 6 + len(_footnote_lines(caption)) * (FOOTNOTE_SIZE + 5) + PAD - 8


def _columns_that_fit(count: int, columns: int, needed: float) -> int:
    """As many columns as the caller asked for, fewer when the labels need the room.

    A panel narrower than its own labels would leave no bar to read, so the layout gives up
    columns rather than shrinking the plot to nothing.
    """
    columns = max(1, min(columns, count))
    while columns > 1:
        width = (WIDTH - 2 * PAD - (columns - 1) * PANEL_GAP) / columns
        if width >= needed:
            break
        columns -= 1
    return columns


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


def _open(
    caption: Caption,
    theme: Theme,
    height: float,
    *,
    x_scale: str = "linear",
    y_scale: str = "linear",
) -> Canvas:
    canvas = Canvas(WIDTH, height, theme, label=caption.label, x_scale=x_scale, y_scale=y_scale)
    canvas.rect(0.5, 0.5, WIDTH - 1, height - 1, theme.surface, radius=8, stroke=theme.border)
    y = PAD + TITLE_SIZE
    canvas.text(PAD, y, caption.title, size=TITLE_SIZE, weight=600)
    for line in _subtitle_lines(caption):
        y += LINE_HEIGHT
        canvas.text(PAD, y, line, size=SUBTITLE_SIZE, fill=theme.secondary)
    return canvas


def _close(canvas: Canvas, caption: Caption, grid_bottom: float) -> str:
    y = grid_bottom + 6
    for line in _footnote_lines(caption):
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


def bar_panels(
    caption: Caption,
    panels: Sequence[BarPanel],
    theme: Theme,
    *,
    columns: int = 2,
    axis_label: str = "",
) -> str:
    """Horizontal bars, one panel per group. Each panel has its own scale, so compare
    bars inside a panel; the printed values carry the comparison across panels.

    `axis_label` names the quantity and its unit under each column of panels, so a bar has a
    scale a reader can hold, not only a number at its tip. Every bar also carries its own
    setup name and value, so no legend is needed to read it.
    """
    if not panels:
        raise ValueError("no panels")
    all_rows = [row for panel in panels for row in panel.rows]
    label_w = _label_width([row.label for row in all_rows])
    value_w = _value_width(all_rows)
    panel_height = PANEL_TITLE_HEIGHT + max(len(panel.rows) for panel in panels) * ROW_PITCH
    top = _header_height(caption)
    columns = _columns_that_fit(len(panels), columns, label_w + value_w + 40)
    origins, panel_width, bottom = _grid(len(panels), columns, panel_height, top)
    track = panel_width - label_w - value_w
    if track < 40:
        raise ValueError("labels leave no room for the bars; use fewer columns")
    room = AXIS_LABEL_HEIGHT if axis_label else 0.0

    canvas = _open(caption, theme, bottom + room + _footer_height(caption))
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
    if axis_label:
        # One title under each column of panels: every panel has its own scale, so each needs its own
        # axis name, and a single column needs the name only once.
        for left in sorted({px for px, _ in origins}):
            canvas.text(left + panel_width / 2, bottom + 16, axis_label, size=NOTE_SIZE, fill=theme.muted, anchor="middle")
    return _close(canvas, caption, bottom + room)


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
    axis_label: str = "",
) -> str:
    """A dot for the measured rate and a line for its interval, one row per setting.

    Every panel shares the same axis, so overlap between rows and panels can be read
    directly. The axis does not start at zero: position, not length, carries the value.
    `axis_label` names the quantity under the picture, and every row carries its own
    setting name and value.
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
    columns = _columns_that_fit(len(panels), columns, label_w + value_w + 60)
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
        if axis_label:
            canvas.text(
                x0 + track / 2,
                rows_bottom + 30,
                axis_label,
                size=NOTE_SIZE,
                fill=theme.muted,
                anchor="middle",
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


def _legend(canvas: Canvas, series: Sequence[LineSeries], y: float) -> None:
    """Series names in one row above the plot, each after a swatch in its own colour."""
    x = PAD
    for line in series:
        canvas.line(x, y - 4, x + 14, y - 4, canvas.theme.series[line.series], width=2, round_cap=True)
        canvas.text(x + 20, y, line.label, size=NOTE_SIZE, fill=canvas.theme.secondary)
        x += 20 + text_width(line.label, NOTE_SIZE) + 24


def _check_log_panel(panel: LinePanel) -> None:
    if not panel.series:
        raise ValueError("no series")
    if min(panel.x_min, panel.y_min) <= 0 or panel.x_max <= panel.x_min or panel.y_max <= panel.y_min:
        raise ValueError("log axes need a positive range")
    if not any(point for series in panel.series for point in series.points):
        raise ValueError("no points")


def _log_span(low: float, high: float):
    """Map a value in `low` to `high` onto 0 to 1 along a log scale, clamped to the ends."""
    floor, span = math.log10(low), math.log10(high) - math.log10(low)
    return lambda value: (math.log10(min(max(value, low), high)) - floor) / span


def _place_value(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    plot_left: float,
    plot_right: float,
    plot_bottom: float,
    placed: List[Tuple[float, float, float, float]],
) -> None:
    """Put a point's value beside it, in the first spot that no other label holds.

    A picture is read as a still image, so every point prints its value; where two lines run close
    together the label moves above or below its point rather than on top of its neighbour.
    """
    wide = text_width(text, NOTE_SIZE)
    # Above the point first, then one line higher, then below: a second line's label moves out of
    # the way before it lands on its neighbour's row.
    boxes = tuple(
        (x + gap, y + lift, anchor)
        for lift in (-8, -21, -34, -47, 15, 28, 41)
        for gap, anchor in ((8, "start"), (-8, "end"))
    )
    for cx, cy, anchor in boxes:
        left = cx if anchor == "start" else cx - wide
        right = left + wide
        top, bottom = cy - NOTE_SIZE, cy + 2
        if left < plot_left or right > plot_right or bottom > plot_bottom - 2:
            continue
        if any(not (right < held_left or left > held_right or bottom < held_top or top > held_bottom)
               for held_left, held_top, held_right, held_bottom in placed):
            continue
        placed.append((left, top, right, bottom))
        canvas.text(cx, cy, text, size=NOTE_SIZE, fill=canvas.theme.muted, anchor=anchor)
        return
    # Every spot near the point is taken: keep the value beside it all the same, inside the picture.
    cx = min(max(x + 8, plot_left), plot_right - 4 - wide)
    placed.append((cx, y - 8 - NOTE_SIZE, cx + wide, y - 6))
    canvas.text(cx, y - 8, text, size=NOTE_SIZE, fill=canvas.theme.muted)


def _draw_plot(
    canvas: Canvas,
    panel: LinePanel,
    left: float,
    top: float,
    right: float,
    bottom: float,
    reserved: Sequence[Tuple[float, float, float, float]] = (),
) -> None:
    """Both log axes, their grids and ticks, and every series of one panel, inside a box.

    The caller owns the box, so the same marks serve a chart that fills the figure and one that
    shares it with other panels. `reserved` holds the boxes already spoken for (a panel title), so
    a value label does not land on one.
    """
    across, down = _log_span(panel.x_min, panel.x_max), _log_span(panel.y_min, panel.y_max)

    def x_of(value: float) -> float:
        return left + across(value) * (right - left)

    def y_of(value: float) -> float:
        return bottom - down(value) * (bottom - top)

    for value, label in panel.y_ticks:
        y = y_of(value)
        canvas.line(left, y, right, y, canvas.theme.grid)
        canvas.text(left - 8, y + 4, label, size=NOTE_SIZE, fill=canvas.theme.muted, anchor="end")
    for value, label in panel.x_ticks:
        x = x_of(value)
        canvas.line(x, top, x, bottom, canvas.theme.grid)
        canvas.text(x, bottom + 14, label, size=NOTE_SIZE, fill=canvas.theme.muted, anchor="middle")
    canvas.line(left, top, left, bottom, canvas.theme.axis)
    canvas.line(left, bottom, right, bottom, canvas.theme.axis)

    placed: List[Tuple[float, float, float, float]] = list(reserved)
    for series in panel.series:
        colour = canvas.theme.series[series.series]
        placed_points = [(x_of(point.x), y_of(point.y)) for point in series.points]
        for (x1, y1), (x2, y2) in zip(placed_points, placed_points[1:]):
            canvas.line(x1, y1, x2, y2, colour, width=2, round_cap=True)
        for point, (x, y) in zip(series.points, placed_points):
            canvas.dot(
                x,
                y,
                4,
                colour,
                ring=canvas.theme.surface,
                tooltip=f"{panel.title} · {series.label} · {point.x_text}: {point.y_text}",
            )
    for series in panel.series:
        for point in series.points:
            _place_value(canvas, point.y_text, x_of(point.x), y_of(point.y), left, right, bottom, placed)


AXIS_LABEL_ROOM = 30


def _axis_room(panel: LinePanel) -> float:
    """Left margin a rotated y-axis name needs, or none when the panel has no y name."""
    return 18.0 if panel.y_label else 0.0


def _axis_labels(
    canvas: Canvas,
    panel: LinePanel,
    x_centre: float,
    y_centre: float,
    plot_bottom: float,
    left_edge: float,
    *,
    draw_y: bool = True,
) -> None:
    """The two axis names: one turned on its side at the left, one under the x ticks."""
    if panel.y_label and draw_y:
        canvas.text(
            left_edge + 4,
            y_centre,
            panel.y_label,
            size=NOTE_SIZE,
            fill=canvas.theme.muted,
            anchor="middle",
            rotate=-90,
        )
    if panel.x_label:
        canvas.text(
            x_centre,
            plot_bottom + 28,
            panel.x_label,
            size=NOTE_SIZE,
            fill=canvas.theme.muted,
            anchor="middle",
        )


def line_panel(caption: Caption, panel: LinePanel, theme: Theme) -> str:
    """One line per series, against a value that runs across decades, on log axes.

    Position carries the value on both axes, so a straight line means a constant growth
    rate. Every point gets its value in a tooltip rather than a label: on a line, labels
    collide where two series meet.
    """
    _check_log_panel(panel)
    gutter = max([text_width(label, NOTE_SIZE) for _, label in panel.y_ticks] + [24.0]) + 12
    left, right = PAD + gutter + _axis_room(panel), WIDTH - PAD - 24
    top = _header_height(caption) + LEGEND_ROW_HEIGHT + 4
    bottom = top + LINE_PLOT_HEIGHT
    room = AXIS_LABEL_HEIGHT if panel.x_label else 0

    canvas = _open(
        caption, theme, bottom + LEGEND_ROW_HEIGHT + room + _footer_height(caption), x_scale="log", y_scale="log"
    )
    _legend(canvas, panel.series, top - LEGEND_ROW_HEIGHT + 4)
    _draw_plot(canvas, panel, left, top, right, bottom)
    _axis_labels(canvas, panel, (left + right) / 2, (top + bottom) / 2, bottom, PAD)
    return _close(canvas, caption, bottom + LEGEND_ROW_HEIGHT + room - 6)


def line_panels(caption: Caption, panels: Sequence[LinePanel], theme: Theme, *, columns: int = 2) -> str:
    """One line chart per panel, side by side, on axes the caller has made the same for all.

    The panels share their ranges, so a line can be read against the line of the panel next to
    it and a straight line means the same growth rate in both. Each point keeps its value in a
    tooltip, and each panel keeps its own title.
    """
    if not panels:
        raise ValueError("no panels")
    for panel in panels:
        _check_log_panel(panel)
    gutter = max(
        [text_width(label, NOTE_SIZE) for panel in panels for _, label in panel.y_ticks] + [24.0]
    ) + 12
    gutter += max(_axis_room(panel) for panel in panels)
    panel_height = PANEL_TITLE_HEIGHT + PANEL_PLOT_HEIGHT + AXIS_LABEL_HEIGHT
    top = _header_height(caption) + LEGEND_ROW_HEIGHT + 4
    origins, panel_width, bottom = _grid(len(panels), columns, panel_height, top)
    if panel_width - gutter < 60:
        raise ValueError("labels leave no room for the plot; use fewer columns")

    series: List[LineSeries] = []
    for panel in panels:
        for line in panel.series:
            if line.label not in [known.label for known in series]:
                series.append(line)

    room = AXIS_LABEL_HEIGHT if any(panel.x_label for panel in panels) else 0
    canvas = _open(caption, theme, bottom + room + _footer_height(caption), x_scale="log", y_scale="log")
    _legend(canvas, series, top - LEGEND_ROW_HEIGHT + 4)
    for index, (panel, (px, py)) in enumerate(zip(panels, origins)):
        canvas.text(px, py + PANEL_TITLE_SIZE, panel.title, size=PANEL_TITLE_SIZE, weight=600)
        plot_top = py + PANEL_TITLE_HEIGHT
        plot_bottom = plot_top + PANEL_PLOT_HEIGHT
        left, right = px + gutter, px + panel_width
        title_box = (
            px,
            py - 2.0,
            px + text_width(panel.title, PANEL_TITLE_SIZE, bold=True),
            py + PANEL_TITLE_SIZE + 3,
        )
        _draw_plot(canvas, panel, left, plot_top, right, plot_bottom, reserved=(title_box,))
        # One name for the shared y axis, on the first panel only, so it is not repeated.
        _axis_labels(
            canvas,
            panel,
            (left + right) / 2,
            (plot_top + plot_bottom) / 2,
            plot_bottom,
            PAD,
            draw_y=index == 0,
        )
    return _close(canvas, caption, bottom + room)

