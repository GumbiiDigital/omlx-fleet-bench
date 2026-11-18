"""Load benchmark matrices and expand cells in A/B run order."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


SETTING_FIELDS = (
    "prefill_helper_node_id",
    "prefill_helper_layers",
    "qwen35_ane_prefill_enabled",
    "turboquant_kv_enabled",
    "turboquant_kv_scheme",
    "turboquant_kv_bits",
    "turboquant_skip_last",
)

ALIGN_PROMPT_TO_ANE = "align_prompt_to_ane"
HELPER_OFF_NODE_ID = ""


def merge_settings(
    base: Dict[str, Any],
    patch: Dict[str, Any],
    *,
    helper_on: bool,
    ane_on: bool,
    helper_node_id: str,
) -> Dict[str, Any]:
    """Full model settings for one run: the matrix base, the variant patch, then the flags.

    The flags win over the patch, and the helper node id is sent only when the helper is on.
    """
    merged = dict(base)
    merged.update(patch)
    merged["qwen35_ane_prefill_enabled"] = ane_on
    merged["prefill_helper_node_id"] = helper_node_id if helper_on else HELPER_OFF_NODE_ID
    return merged


def variant_flags(variant: Dict[str, Any]) -> Tuple[bool, bool]:
    """Whether a matrix variant asks for the helper and for the ANE."""
    helper = variant.get("helper", "off")
    ane = variant.get("ane", "off")
    helper_on = str(helper).lower() in ("on", "true", "1", "yes")
    ane_on = str(ane).lower() in ("on", "true", "1", "yes")
    return helper_on, ane_on


def variant_settings_patch(variant: Dict[str, Any]) -> Dict[str, Any]:
    """The model settings a variant changes, keeping only the fields a matrix may set."""
    return {k: v for k, v in (variant.get("settings") or {}).items() if k in SETTING_FIELDS}


@dataclass(frozen=True)
class SettingsVariant:
    """One setting under test: its name, its two flags and the settings it changes."""

    name: str
    helper_on: bool
    ane_on: bool
    settings_patch: Dict[str, Any] = field(default_factory=dict)

    def merge_settings(self, base: Dict[str, Any], helper_node_id: str) -> Dict[str, Any]:
        return merge_settings(
            base,
            self.settings_patch,
            helper_on=self.helper_on,
            ane_on=self.ane_on,
            helper_node_id=helper_node_id,
        )


def settings_variant(raw: Dict[str, Any]) -> SettingsVariant:
    """One variant as a matrix file writes it."""
    helper_on, ane_on = variant_flags(raw)
    return SettingsVariant(
        name=str(raw["name"]),
        helper_on=helper_on,
        ane_on=ane_on,
        settings_patch=variant_settings_patch(raw),
    )


@dataclass
class RunSpec:
    """One scheduled benchmark run."""

    model: str
    variant: str
    prompt_size: int
    repeat_index: int
    helper_on: bool
    ane_on: bool
    settings_patch: Dict[str, Any] = field(default_factory=dict)
    matrix_path: str = ""

    @property
    def cell_key(self) -> str:
        return f"{self.variant}:{self.prompt_size}"

    def merge_settings(
        self,
        base: Dict[str, Any],
        helper_node_id: str,
    ) -> Dict[str, Any]:
        """Build full model settings for this run."""
        return merge_settings(
            base,
            self.settings_patch,
            helper_on=self.helper_on,
            ane_on=self.ane_on,
            helper_node_id=helper_node_id,
        )


def load_matrix(path: str) -> Dict[str, Any]:
    """Load a matrix JSON file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if ALIGN_PROMPT_TO_ANE in data and data[ALIGN_PROMPT_TO_ANE] is False:
        raise ValueError(
            "align_prompt_to_ane must stay true (private runs only); refuse matrix"
        )
    return data


def expand_runs(
    matrix: Dict[str, Any],
    *,
    matrix_path: str = "",
    only_cells: Optional[Sequence[str]] = None,
) -> List[RunSpec]:
    """Expand matrix into ordered run specs (repeat -> size -> variant)."""
    if ALIGN_PROMPT_TO_ANE in matrix and matrix[ALIGN_PROMPT_TO_ANE] is False:
        raise ValueError(
            "align_prompt_to_ane must stay true (private runs only); refuse matrix"
        )
    model = matrix["model"]
    base_settings = dict(matrix.get("base_settings") or {})
    variants = matrix["variants"]
    sizes: List[int] = [int(s) for s in matrix["prompt_sizes"]]
    runs_per_cell = int(matrix.get("runs_per_cell", 3))
    filter_set = set(only_cells) if only_cells else None

    specs: List[RunSpec] = []
    for repeat in range(runs_per_cell):
        for size in sizes:
            for variant in variants:
                name = variant["name"]
                cell_key = f"{name}:{size}"
                if filter_set is not None and cell_key not in filter_set:
                    continue
                helper_on, ane_on = variant_flags(variant)
                patch = variant_settings_patch(variant)
                specs.append(
                    RunSpec(
                        model=model,
                        variant=name,
                        prompt_size=size,
                        repeat_index=repeat,
                        helper_on=helper_on,
                        ane_on=ane_on,
                        settings_patch=patch,
                        matrix_path=matrix_path,
                    )
                )
    return specs


def load_and_expand(
    path: str,
    only_cells: Optional[Sequence[str]] = None,
) -> List[RunSpec]:
    """Load matrix file and return expanded runs."""
    matrix = load_matrix(path)
    return expand_runs(matrix, matrix_path=str(Path(path)), only_cells=only_cells)


def settings_fields_touched(specs: Sequence[RunSpec], base: Dict[str, Any]) -> List[str]:
    """Return setting field names that any run may change."""
    fields = set(SETTING_FIELDS)
    for spec in specs:
        for key in spec.settings_patch:
            if key in SETTING_FIELDS:
                fields.add(key)
    for key in base:
        if key in SETTING_FIELDS:
            fields.add(key)
    return sorted(fields)