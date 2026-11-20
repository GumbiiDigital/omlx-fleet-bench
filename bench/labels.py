"""Display names, order and chart colour for matrix variants.

One place, so a variant looks the same in every table and chart. A variant that is not
listed here still works: it keeps its matrix name and takes the next free colour.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

VARIANT_LABELS: Dict[str, str] = {
    "gpu": "Mac alone",
    "native": "Native KV cache",
    "affine4": "Affine4 KV cache",
    "affine8": "Affine8 KV cache",
    "ane": "+ ANE (Apple chip)",
    "spark": "+ Spark helper",
    "ane_spark": "+ ANE + Spark helper",
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

# A layer setting is named by what the request asked for: the Mac on its own, the helper's own
# choice of layers, or a pinned count. The count itself is read from the row, never typed in.
SETTING_MAC_ALONE = "mac-alone"
SETTING_AUTOMATIC = "automatic"
LAYER_SETTING_PREFIX = "layers-"

# An arm is what a wave of many requests ran on: the Mac alone, or the Mac with its helper.
# The arm comes from the row (whether the helper was on), never from a list of variant names.
ARM_ALONE = "mac-alone"
ARM_HELPER = "helper"

ARM_LABELS: Dict[str, str] = {ARM_ALONE: "Mac alone", ARM_HELPER: "Mac + Spark"}

# The Mac alone keeps the baseline blue; the helper keeps the aqua it has in every other chart.
ARM_ORDER: List[str] = [ARM_ALONE, ARM_HELPER]
ARM_SERIES: Dict[str, str] = {ARM_ALONE: "blue", ARM_HELPER: "aqua"}

SETTING_LABELS: Dict[str, str] = {SETTING_MAC_ALONE: "Mac alone", SETTING_AUTOMATIC: "Automatic"}

# Colour follows the setting, in the order the settings are shown: the Mac alone keeps the
# baseline blue, then the helper settings take the checked slots (blue, magenta, violet,
# orange, aqua) in turn.
SETTING_SERIES: List[str] = ["blue", "magenta", "violet", "orange", "aqua", "yellow", "green", "red"]


def variant_label(name: str) -> str:
    return VARIANT_LABELS.get(name, name)


def layer_setting(count: int) -> str:
    """The setting name for a pinned layer count."""
    return f"{LAYER_SETTING_PREFIX}{int(count)}"


def layer_count(name: str) -> Optional[int]:
    """The pinned layer count in a setting name, or None when it pins none."""
    if not name.startswith(LAYER_SETTING_PREFIX):
        return None
    try:
        return int(name[len(LAYER_SETTING_PREFIX) :])
    except ValueError:
        return None


def setting_label(name: str) -> str:
    """'mac-alone' -> 'Mac alone', 'layers-32' -> '32 layers'."""
    if name in SETTING_LABELS:
        return SETTING_LABELS[name]
    count = layer_count(name)
    return f"{count} layers" if count is not None else name


def ordered_settings(names: Iterable[str]) -> List[str]:
    """The Mac alone, then the automatic choice, then pinned layer counts from fewest to most."""
    unique = set(names)
    head = [name for name in (SETTING_MAC_ALONE, SETTING_AUTOMATIC) if name in unique]
    pinned = sorted((name for name in unique if layer_count(name) is not None), key=lambda name: layer_count(name) or 0)
    rest = sorted(unique - set(head) - set(pinned))
    return head + pinned + rest


def setting_series(names: Iterable[str], slots: Optional[List[str]] = None) -> Dict[str, str]:
    """Colour slot per setting, in the setting order. Runs out loudly rather than repeating."""
    slots = list(SETTING_SERIES if slots is None else slots)
    out: Dict[str, str] = {}
    for name in ordered_settings(names):
        if not slots:
            raise ValueError(f"no chart colour left for setting {name!r}; add one to bench/labels.py")
        out[name] = slots.pop(0)
    return out


def ordered_variants(names: Iterable[str]) -> List[str]:
    """Known variants in the fixed order, then unknown ones by name."""
    unique = set(names)
    known = [name for name in VARIANT_ORDER if name in unique]
    return known + sorted(unique - set(known))


def arm_label(name: str) -> str:
    """'mac-alone' -> 'Mac alone', 'helper' -> 'With helper'."""
    return ARM_LABELS.get(name, name)


def ordered_arms(names: Iterable[str]) -> List[str]:
    """Known arms in the fixed order (the Mac alone first), then any other by name."""
    unique = set(names)
    known = [name for name in ARM_ORDER if name in unique]
    return known + sorted(unique - set(known))


def arm_series(names: Iterable[str]) -> Dict[str, str]:
    """Colour slot per arm. An arm with no slot is an error, not a guess."""
    out: Dict[str, str] = {}
    for name in ordered_arms(names):
        if name not in ARM_SERIES:
            raise ValueError(f"no chart colour for arm {name!r}; add it to bench/labels.py")
        out[name] = ARM_SERIES[name]
    return out


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
