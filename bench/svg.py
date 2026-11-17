"""A very small SVG writer: themes, a canvas, and the few marks the charts need.

Standard library only. Output is deterministic (fixed number formatting, no timestamps),
so a chart built twice from the same rows is byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from xml.sax.saxutils import escape, quoteattr

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

# Average glyph width as a fraction of the font size. Used only to place a note after a
# value label; the layouts leave slack, so an estimate is enough.
GLYPH_WIDTH = 0.56
BOLD_GLYPH_WIDTH = 0.62


@dataclass(frozen=True)
class Theme:
    """Colours for one page background. Series colours are keyed by slot name."""

    name: str
    surface: str
    border: str
    ink: str
    secondary: str
    muted: str
    grid: str
    axis: str
    series: Dict[str, str] = field(default_factory=dict)


# Categorical slots were checked for colour-vision separation in the orders the charts
# use: blue, orange, aqua, yellow (speed) and blue, magenta, violet, orange, aqua (quality).
LIGHT = Theme(
    name="light",
    surface="#fcfcfb",
    border="#e1e0d9",
    ink="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    series={
        "blue": "#2a78d6",
        "orange": "#eb6834",
        "aqua": "#1baf7a",
        "yellow": "#eda100",
        "magenta": "#e87ba4",
        "violet": "#6250d6",
        "green": "#008300",
        "red": "#e34948",
    },
)

DARK = Theme(
    name="dark",
    surface="#1a1a19",
    border="#2c2c2a",
    ink="#f0efec",
    secondary="#c3c2b7",
    muted="#898781",
    grid="#2c2c2a",
    axis="#383835",
    series={
        "blue": "#3987e5",
        "orange": "#d95926",
        "aqua": "#199e70",
        "yellow": "#c98500",
        "magenta": "#d55181",
        "violet": "#9085e9",
        "green": "#0ca30c",
        "red": "#e66767",
    },
)

THEMES: Dict[str, Theme] = {LIGHT.name: LIGHT, DARK.name: DARK}


def num(value: float) -> str:
    """Format a coordinate: at most two decimals, no trailing zeros."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def text_width(text: str, size: float, *, bold: bool = False) -> float:
    """Rough rendered width of `text` at `size` px."""
    return len(text) * size * (BOLD_GLYPH_WIDTH if bold else GLYPH_WIDTH)


class Canvas:
    """Collects SVG elements and renders one document."""

    def __init__(self, width: float, height: float, theme: Theme, *, label: str) -> None:
        self.width = width
        self.height = height
        self.theme = theme
        self.label = label
        self._parts: List[str] = []

    def _tooltip(self, tooltip: Optional[str]) -> str:
        return f"<title>{escape(tooltip)}</title>" if tooltip else ""

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        fill: str,
        *,
        radius: float = 0,
        stroke: Optional[str] = None,
    ) -> None:
        extra = f' rx="{num(radius)}"' if radius else ""
        if stroke:
            extra += f' stroke="{stroke}" stroke-width="1"'
        self._parts.append(
            f'<rect x="{num(x)}" y="{num(y)}" width="{num(width)}" height="{num(height)}" '
            f'fill="{fill}"{extra}/>'
        )

    def bar(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        fill: str,
        *,
        radius: float = 4,
        tooltip: Optional[str] = None,
    ) -> None:
        """Horizontal bar growing right from `x`: square at the baseline, rounded at the data end."""
        width = max(width, 0.0)
        r = min(radius, width, height / 2)
        path = (
            f"M{num(x)},{num(y)} H{num(x + width - r)} "
            f"Q{num(x + width)},{num(y)} {num(x + width)},{num(y + r)} "
            f"V{num(y + height - r)} "
            f"Q{num(x + width)},{num(y + height)} {num(x + width - r)},{num(y + height)} "
            f"H{num(x)} Z"
        )
        self._parts.append(f'<path d="{path}" fill="{fill}">{self._tooltip(tooltip)}</path>')

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        stroke: str,
        *,
        width: float = 1,
        round_cap: bool = False,
    ) -> None:
        cap = ' stroke-linecap="round"' if round_cap else ""
        self._parts.append(
            f'<line x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}" '
            f'stroke="{stroke}" stroke-width="{num(width)}"{cap}/>'
        )

    def dot(
        self,
        cx: float,
        cy: float,
        radius: float,
        fill: str,
        *,
        ring: Optional[str] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        """Filled marker; `ring` draws a 2px surface-coloured ring so it reads over a line."""
        extra = f' stroke="{ring}" stroke-width="2"' if ring else ""
        self._parts.append(
            f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(radius)}" fill="{fill}"{extra}>'
            f"{self._tooltip(tooltip)}</circle>"
        )

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        size: float = 12,
        fill: Optional[str] = None,
        anchor: str = "start",
        weight: Optional[int] = None,
    ) -> None:
        attrs = f'x="{num(x)}" y="{num(y)}" font-size="{num(size)}" fill="{fill or self.theme.ink}"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if weight:
            attrs += f' font-weight="{weight}"'
        self._parts.append(f"<text {attrs}>{escape(content)}</text>")

    def render(self) -> str:
        width, height = num(self.width), num(self.height)
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label={quoteattr(self.label)} '
            f'font-family="{FONT_FAMILY}">'
        )
        return "\n".join([head, f"<title>{escape(self.label)}</title>", *self._parts, "</svg>"]) + "\n"
