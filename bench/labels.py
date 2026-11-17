"""Display names, order and chart colour for matrix variants.

One place, so a variant looks the same in every table and chart. A variant that is not
listed here still works: it keeps its matrix name and takes the next free colour.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

VARIANT_LABELS: Dict[str, str] = {
    "gpu": "GPU only",
    "native": "Native KV",
    "affine4": "Affine4 KV",
    "affine8": "Affine8 KV",
    "ane": "+ ANE prefill",
    "spark": "+ Spark helper",
    "ane_spark": "+ ANE + Spark",
}

# Colour follows the variant, not its position in a chart. "gpu" and "native" are the
# same configuration under two matrix names, so they share a colour.
VARIANT_SERIES: Dict[str, str] = {
    "gpu": "blue",
    "native": "blue",
    "affine4": "magenta",
    "affine8": "violet",
    "ane": "orange",
    "spark": "aqua",
    "ane_spark": "yellow",
}

# Row order in tables and charts. Neighbouring colours in this order were checked for
# colour-vision separation; keep new entries at the end.
VARIANT_ORDER: List[str] = ["gpu", "native", "affine4", "affine8", "ane", "spark", "ane_spark"]

SPARE_SERIES: List[str] = ["green", "red"]


def variant_label(name: str) -> str:
    return VARIANT_LABELS.get(name, name)


def ordered_variants(names: Iterable[str]) -> List[str]:
    """Known variants in the fixed order, then unknown ones by name."""
    unique = set(names)
    known = [name for name in VARIANT_ORDER if name in unique]
    return known + sorted(unique - set(known))


def variant_series(names: Iterable[str]) -> Dict[str, str]:
    """Colour slot per variant. Unknown variants take the spare slots in name order."""
    out: Dict[str, str] = {}
    spare = iter(SPARE_SERIES)
    for name in ordered_variants(names):
        if name in VARIANT_SERIES:
            out[name] = VARIANT_SERIES[name]
            continue
        try:
            out[name] = next(spare)
        except StopIteration:
            raise ValueError(
                f"no chart colour left for variant {name!r}; add it to bench/labels.py"
            ) from None
    return out


def size_label(tokens: int) -> str:
    """8192 -> '8K', 131072 -> '128K', 1000 -> '1,000'."""
    if tokens >= 1024 and tokens % 1024 == 0:
        return f"{tokens // 1024}K"
    return f"{tokens:,}"
