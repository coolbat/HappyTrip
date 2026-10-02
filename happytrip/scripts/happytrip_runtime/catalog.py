"""Validated, local-only mode registry. Only the selected mode card is read."""
from copy import deepcopy
import json
from pathlib import Path
import re
from .types import HappyTripError

MODE_IDS = tuple([f"A{i:02d}" for i in range(1, 13)] + ["B01", "B03", "B04", "B14", "B16", "B22"])
SCOPES = {"masked_edit", "global_adjust", "reimagine", "hybrid_layout", "overlay"}
VARIABLES = {"input_summary", "target_summary", "protected_summary", "facts_summary", "layout_summary", "text_summary", "mode_options_summary", "extra_notes"}


def load_catalog(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[2] / "references" / "catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HappyTripError("CATALOG_INVALID", f"Cannot read catalog: {exc}") from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("modes"), list):
        raise HappyTripError("CATALOG_INVALID", "Catalog must contain a modes array")
    root = path.resolve().parent.parent
    modes = catalog["modes"]
    ids = [m.get("id") if isinstance(m, dict) else None for m in modes]
    if any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or set(ids) != set(MODE_IDS) or catalog.get("mode_count") != 18:
        raise HappyTripError("CATALOG_INVALID", "Catalog must contain exactly the 18 unique V1 mode IDs")
    declared = catalog.get("template_variables", [])
    if not isinstance(declared, list) or any(not isinstance(v, str) for v in declared) or set(declared) != VARIABLES:
        raise HappyTripError("CATALOG_INVALID", "Catalog template variables do not match the eight public variables")
    if sum(m.get("validation_priority") == "P0" for m in modes) != 8:
        raise HappyTripError("CATALOG_INVALID", "V1 catalog requires eight P0 modes")
    for mode in modes:
        if mode.get("edit_scope") not in SCOPES:
            raise HappyTripError("CATALOG_INVALID", f"Invalid edit scope for {mode['id']}")
        lo, hi = mode.get("input_min"), mode.get("input_max")
        if type(lo) is not int or type(hi) is not int or not 1 <= lo <= hi:
            raise HappyTripError("CATALOG_INVALID", f"Invalid input range for {mode['id']}")
        relative = mode.get("mode_file")
        if not isinstance(relative, str):
            raise HappyTripError("CATALOG_INVALID", f"Missing mode card for {mode['id']}")
        card = (root / relative).resolve()
        if not card.is_relative_to(root) or not card.is_file():
            raise HappyTripError("CATALOG_INVALID", f"Mode card missing or outside skill: {relative}")
    catalog["_root"] = str(root)
    return catalog


def get_mode(catalog, mode_id):
    if not isinstance(mode_id, str):
        raise HappyTripError("MODE_UNKNOWN", "Mode must be a V1 ID")
    normalized = mode_id.strip().upper()
    for entry in catalog["modes"]:
        if entry["id"] == normalized:
            mode = deepcopy(entry)
            card = (Path(catalog["_root"]) / mode["mode_file"]).resolve()
            if not card.is_relative_to(Path(catalog["_root"]).resolve()):
                raise HappyTripError("CATALOG_INVALID", "Mode card escapes skill directory")
            try:
                template = card.read_text(encoding="utf-8")
            except OSError as exc:
                raise HappyTripError("CATALOG_INVALID", f"Cannot read {card}") from exc
            unknown = set(re.findall(r"{{\s*(\w+)\s*}}", template)) - VARIABLES
            if unknown:
                raise HappyTripError("CATALOG_INVALID", f"Undeclared template variables: {', '.join(sorted(unknown))}")
            mode["template_path"] = str(card)
            return mode
    raise HappyTripError("MODE_UNKNOWN", f"Unknown V1 mode: {mode_id}")
