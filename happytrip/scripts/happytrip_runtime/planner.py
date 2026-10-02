"""Auditable per-unit plans. No provider calls, inferred facts, or output files."""
from copy import deepcopy
import hashlib
import json
import math
from .facts import normalize_facts, TRUSTED_SOURCES
from .types import HappyTripError


def route_data_fingerprint(layout):
    """Bind printed facts and map data to the planned composition, excluding styling."""
    data = {key: deepcopy(layout.get(key)) for key in
            ("title", "subtitle", "date_range", "footer", "stops", "basemap", "route_segments")}
    data["footer"] = data["footer"] or []
    data["route_segments"] = data["route_segments"] or []
    data["template"] = layout.get("template", "travel_poster")
    data["map_mode"] = layout.get("map_mode", "itinerary_schematic")
    if data["map_mode"] == "collection":
        data["map_mode"] = "unordered_places"
    data["order_confirmed"] = layout.get("order_confirmed") is True and data["map_mode"] != "unordered_places"
    data["ordered_stop_ids"] = layout.get("ordered_stop_ids", []) if data["order_confirmed"] else []
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _stage(stage_id, kind, photo_ids, instruction, *, depends_on=(), unit=None):
    return {"id": stage_id, "kind": kind, "photo_ids": list(photo_ids),
            "depends_on": list(depends_on), "instruction": instruction,
            "image_calls": int(kind == "generate"), "unit": unit or {"type": "whole"}}


def _ids(assets):
    ids = [asset["photo_id"] if isinstance(asset, dict) else asset for asset in assets]
    if any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
        raise HappyTripError("ASSET_INVALID", "Photo IDs must be unique nonempty strings")
    return ids


def _known_references(ids, known, message):
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
        raise HappyTripError("ASSET_MISSING", message)
    unknown = set(ids) - set(known)
    if unknown:
        raise HappyTripError("ASSET_MISSING", f"Unknown photo IDs: {', '.join(sorted(unknown))}")
    if len(ids) != len(set(ids)):
        raise HappyTripError("ASSET_INVALID", "A unit cannot repeat the same photo ID")


def plan_stickers(assets, selection=None):
    """One independently repairable sticker per selected asset; never drop refs."""
    known = _ids(assets)
    selection = list(known) if selection is None else selection
    if not isinstance(selection, list):
        raise HappyTripError("SELECTION_INVALID", "selected_photo_ids must be an array")
    _known_references(selection, known, "At least one sticker source must be selected")
    return [_stage(f"sticker-{index:02d}", "generate", [photo_id],
                   f"Generate only sticker {index} from photo {photo_id}: a flat watercolor die-cut sticker. Retain its source mapping; do not create the suitcase or other stickers.",
                   unit={"type": "sticker", "index": index, "source_photo_ids": [photo_id], "repair_scope": "stage_only"})
            for index, photo_id in enumerate(selection, 1)]


def plan_comic(panels, references):
    if not isinstance(panels, list) or len(panels) not in (3, 4):
        raise HappyTripError("STORY_INVALID", "A comic requires exactly three or four structured panels")
    known = _ids(references)
    character_ids = [r["photo_id"] for r in references if isinstance(r, dict) and set(r.get("roles", [])) & {"person", "portrait", "identity", "pet"}]
    stages = []
    for index, panel in enumerate(panels, 1):
        if not isinstance(panel, dict) or not isinstance(panel.get("action"), str) or not panel["action"].strip():
            raise HappyTripError("STORY_INVALID", f"Panel {index} requires an action")
        if panel.get("index", index) != index:
            raise HappyTripError("STORY_INVALID", "Panel index must follow the explicit storyboard order")
        if panel.get("basis") not in {"user", "user_provided", "explicit_fiction", "fiction"}:
            raise HappyTripError("STORY_BASIS_UNKNOWN", f"Panel {index} needs user-provided experience or explicitly fictional basis")
        _known_references(panel.get("photo_ids"), known, f"Panel {index} requires photo bindings")
        refs = list(dict.fromkeys(character_ids + panel["photo_ids"]))
        stages.append(_stage(f"panel-{index:02d}", "generate", refs,
                             f"Generate only storyboard panel {index}; reuse the same character references, clothes and visual style. Leave approved dialogue for composition.",
                             unit={"type": "panel", "index": index, "panel": deepcopy(panel), "source_photo_ids": refs, "character_photo_ids": character_ids, "repair_scope": "stage_only"}))
    return stages


def _coordinates(stop):
    record = stop.get("coordinates")
    if not isinstance(record, dict) or record.get("confirmed") is not True or not isinstance(record.get("source"), str) or record.get("source") not in TRUSTED_SOURCES:
        raise HappyTripError("FACT_COORDINATES_UNKNOWN", f"Stop {stop['id']} requires confirmed coordinates and their source")
    values = record.get("value", record)
    if not isinstance(values, dict):
        raise HappyTripError("FACT_COORDINATES_INVALID", "Coordinates require named lat and lon fields, not an ambiguous pair")
    lat, lon = values.get("lat"), values.get("lon")
    if (isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
            or not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        raise HappyTripError("FACT_COORDINATES_INVALID", f"Invalid latitude/longitude for stop {stop['id']}")
    return deepcopy(record)


def _confirmed_record(record, field):
    if (not isinstance(record, dict) or record.get("confirmed") is not True
            or not isinstance(record.get("source"), str) or record["source"] not in TRUSTED_SOURCES):
        raise HappyTripError("FACT_UNCONFIRMED", f"{field} requires a trusted source and confirmed=true")


def _display_fact(record, field):
    """Dates and metrics are printable only with explicit, trusted provenance."""
    _confirmed_record(record, field)
    if not isinstance(record.get("value"), str) or not record["value"].strip():
        raise HappyTripError("FACT_INVALID", f"{field} requires a nonempty display value")


def validate_route_facts(layout):
    """Validate poster annotations for both planned jobs and direct composition.

    User-supplied title/subtitle are display copy. Dates and measured metadata
    retain their fact records rather than being flattened into untraceable text.
    Geographic geometry and basemap provenance are validated separately.
    """
    if not isinstance(layout, dict):
        raise HappyTripError("INPUT_INVALID", "Route layout must be an object")
    for field in ("title", "subtitle"):
        if field in layout and not isinstance(layout[field], str):
            raise HappyTripError("INPUT_INVALID", f"{field} must be a display string")
    if "date_range" in layout:
        _display_fact(layout["date_range"], "date_range")
    stops = layout.get("stops", [])
    if not isinstance(stops, list) or any(not isinstance(stop, dict) for stop in stops):
        raise HappyTripError("FACT_STOPS_INVALID", "stops must be an array of objects")
    for index, stop in enumerate(stops):
        if "date" in stop:
            _display_fact(stop["date"], f"stops[{index}].date")
    footer = layout.get("footer", [])
    if not isinstance(footer, list):
        raise HappyTripError("FACT_INVALID", "footer must be an array of confirmed facts")
    for index, item in enumerate(footer):
        _display_fact(item, f"footer[{index}]")
        if not isinstance(item.get("label"), str) or not item["label"].strip():
            raise HappyTripError("FACT_INVALID", f"footer[{index}] requires a label")
    segments = layout.get("route_segments", [])
    if not isinstance(segments, list):
        raise HappyTripError("FACT_INVALID", "route_segments must be an array")
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise HappyTripError("FACT_INVALID", "Each route segment must be an object")
        _confirmed_record(segment, f"route_segments[{index}]")
        if "distance" in segment:
            _display_fact(segment["distance"], f"route_segments[{index}].distance")


def plan_route(stops, order=None, map_mode="itinerary_schematic"):
    """Passing order means it is confirmed; make_plan enforces that boundary."""
    if not isinstance(map_mode, str) or map_mode not in {"itinerary_schematic", "unordered_places", "geographic"}:
        raise HappyTripError("MAP_MODE_INVALID", f"Unsupported map_mode: {map_mode}")
    if not isinstance(stops, list) or not 2 <= len(stops) <= 15:
        raise HappyTripError("FACT_STOPS_MISSING", "A route requires 2–15 named stops with photo bindings")
    ids = []
    for stop in stops:
        if not isinstance(stop, dict) or not isinstance(stop.get("id"), str) or not stop["id"] or not isinstance(stop.get("name"), str) or not stop["name"].strip():
            raise HappyTripError("FACT_STOPS_INVALID", "Every stop requires a distinct ID and a name")
        if not isinstance(stop.get("photo_ids"), list) or not stop["photo_ids"] or any(not isinstance(i, str) or not i for i in stop["photo_ids"]):
            raise HappyTripError("FACT_STOPS_INVALID", f"Stop {stop['id']} requires photo bindings")
        ids.append(stop["id"])
        if map_mode == "geographic":
            _coordinates(stop)
    if len(ids) != len(set(ids)):
        raise HappyTripError("FACT_STOPS_INVALID", "Stop IDs must be distinct; same-name stops must not be merged")
    if order is not None and (not isinstance(order, list) or any(not isinstance(i, str) for i in order)):
        raise HappyTripError("FACT_ORDER_INVALID", "Order must be an array of stop IDs")
    ordered = list(order or [])
    if ordered and (len(ordered) != len(ids) or len(set(ordered)) != len(ordered) or set(ordered) != set(ids)):
        raise HappyTripError("FACT_ORDER_INVALID", "Confirmed order must include each stop exactly once")
    if map_mode == "unordered_places":
        ordered = []
    validate_route_facts({"stops": stops})
    return {"map_mode": map_mode, "stops": deepcopy(stops), "ordered_stop_ids": ordered,
            "order_confirmed": bool(ordered),
            "edges": [{"from": a, "to": b} for a, b in zip(ordered, ordered[1:])],
            "label": "站点关联示意，非道路导航轨迹" if map_mode == "geographic" else "行程示意，非比例地图",
            "is_road_route": False, "distance_km": None}


def make_plan(request, assets, mode, caps):
    if not isinstance(request.get("mode_options", {}), dict):
        raise HappyTripError("INPUT_INVALID", "mode_options must be an object")
    if not isinstance(request.get("output", {}), dict):
        raise HappyTripError("INPUT_INVALID", "output must be an object")
    mode_id = mode["id"]
    options = deepcopy(mode.get("options", {}))
    options.update(deepcopy(request.get("mode_options", {})))
    known = _ids(assets)
    plan = {"mode": mode_id, "status": "ready", "errors": [], "warnings": [],
            "required_inputs": [], "required_capabilities": [], "missing_capabilities": [],
            "mode_options": options, "default_ratio": mode["default_ratio"], "stages": [], "source_photo_ids": known,
            "call_budget": {"max_image_calls": 4, "max_repairs_per_stage": 1}, "estimated_image_calls": 0}

    def issue(code, message, field=None):
        item = {"code": code, "message": message}
        plan["errors"].append(item)
        if field:
            plan["required_inputs"].append({"field": field, **item})

    def require(capability):
        if capability not in plan["required_capabilities"]:
            plan["required_capabilities"].append(capability)
        if caps.get(capability) is not True and not any(x["capability"] == capability for x in plan["missing_capabilities"]):
            plan["missing_capabilities"].append({"capability": capability, "available": caps.get(capability, "unknown")})

    try:
        plan["facts"] = normalize_facts(request)
        plan["warnings"].extend(plan["facts"]["warnings"])
    except HappyTripError as exc:
        issue(exc.code, str(exc), "facts")
        plan["facts"] = {"confirmed": [], "hypotheses": [], "warnings": []}
    budget = request.get("budget", {})
    if not isinstance(budget, dict):
        issue("BUDGET_INVALID", "budget must be an object", "budget")
        budget = {}
    for key, default in plan["call_budget"].items():
        value = budget.get(key, default)
        if type(value) is not int or value < 0:
            issue("BUDGET_INVALID", f"{key} must be a nonnegative integer", f"budget.{key}")
        else:
            plan["call_budget"][key] = value
    if any(key in budget for key in ("max_cost", "currency", "max_amount", "price_limit")):
        issue("BUDGET_QUOTE_REQUIRED", "A monetary budget requires a verified provider quote and enforcement; this runtime only enforces image-call counts", "budget")
    raw_contract = request.get("edit_contract", {})
    if not isinstance(raw_contract, dict):
        issue("CONTRACT_CONFLICT", "edit_contract must be an object", "edit_contract")
        raw_contract = {}
    scope = mode["edit_scope"]
    protections = request.get("protected", [])
    strict_default = mode_id == "B01" or (isinstance(protections, list) and any(isinstance(p, dict) and p.get("strict_original") is True for p in protections))
    contract = {"scope": scope, "preserve_identity": True, "preserve_geometry": scope != "reimagine",
                "strict_original": strict_default, "protected_photo_ids": [], "allowed_regions": deepcopy(request.get("allowed_regions", [])),
                "target_descriptions": deepcopy(request.get("targets", [])), "facts_may_be_invented": False,
                "creative_reconstruction": mode_id == "A09"}
    contract.update(deepcopy(raw_contract))
    plan["contract"] = contract
    plan["protected"] = deepcopy(request.get("protected", []))
    plan["allowed_regions"] = contract["allowed_regions"]
    if contract["scope"] != scope:
        issue("CONTRACT_CONFLICT", "The requested edit scope conflicts with the selected mode", "edit_contract.scope")
    for key in ("preserve_identity", "preserve_geometry", "strict_original", "facts_may_be_invented", "creative_reconstruction"):
        if type(contract.get(key)) is not bool:
            issue("CONTRACT_CONFLICT", f"{key} must be a boolean", f"edit_contract.{key}")
    if contract.get("facts_may_be_invented"):
        issue("CONTRACT_CONFLICT", "Invented material must be explicitly labeled fiction, never recorded as confirmed facts", "edit_contract.facts_may_be_invented")
    if contract.get("strict_original") and scope in {"global_adjust", "reimagine"}:
        issue("CONTRACT_CONFLICT", "This mode changes original pixels; full strict-original protection conflicts with it", "edit_contract.strict_original")
    if mode_id == "A09" and (not contract.get("creative_reconstruction") or contract.get("preserve_pose") is True or contract.get("lock_pose") is True):
        issue("CONTRACT_CONFLICT", "Concert reconstruction conflicts with a locked pose or denied creative reconstruction", "edit_contract")
    if scope == "reimagine" and raw_contract.get("preserve_geometry") is True:
        issue("CONTRACT_CONFLICT", "Artistic reconstruction cannot promise unchanged scene geometry", "edit_contract.preserve_geometry")
    if scope == "reimagine" and request.get("preserve_background") is True:
        issue("CONTRACT_CONFLICT", "Artistic reconstruction conflicts with the requested unchanged background", "preserve_background")
    suitcase_ids = [a["photo_id"] for a in assets if set(a.get("roles", [])) & {"suitcase", "suitcase_base", "container"}]
    content_ids = [i for i in known if not (mode_id == "A07" and i in suitcase_ids)]
    if not mode["input_min"] <= len(content_ids) <= mode["input_max"]:
        issue("ASSET_MISSING" if len(content_ids) < mode["input_min"] else "ASSET_COUNT_INVALID",
              f"{mode_id} requires {mode['input_min']}–{mode['input_max']} content photos; got {len(content_ids)}", "photos")
    roles = {role for asset in assets for role in asset.get("roles", [])}
    features = request.get("photo_features", {})
    if isinstance(features, dict):
        roles.update(key for key, value in features.items() if value is True)
    elif isinstance(features, list):
        roles.update(v for v in features if isinstance(v, str))
    if mode_id in {"A04", "A08", "A09", "B14"}:
        required_role = "pet" if mode_id == "A08" and options.get("variant") == "pet_road_trip" else "person"
        eligible = {"person", "portrait", "identity"} if required_role == "person" else {"pet"}
        if not roles & eligible:
            issue("ASSET_ROLE_MISSING", f"{mode_id} requires an explicitly identified {required_role} reference", "photos.roles")
    if mode_id == "B14" and not roles & {"scene", "landscape", "landmark", "background"}:
        issue("ASSET_ROLE_MISSING", "Double exposure requires a scene reference from actual assets", "photos.roles")
    for group_name in ("targets", "protected"):
        group = request.get(group_name, [])
        if not isinstance(group, list):
            issue("TARGET_AMBIGUOUS", f"{group_name} must be an array", group_name)
            continue
        for entry in group:
            if not isinstance(entry, dict) or entry.get("photo_id") not in known:
                issue("ASSET_MISSING", f"Every {group_name} entry must bind a registered photo_id", group_name)
            elif group_name == "targets" and not any(entry.get(k) for k in ("description", "bbox", "mask", "mask_ref", "box")):
                issue("TARGET_AMBIGUOUS", "Each target requires a description, box or mask", "targets")
    protected_ids = contract.get("protected_photo_ids", [])
    if not isinstance(protected_ids, list) or any(i not in known for i in protected_ids):
        issue("ASSET_MISSING", "Protected photo IDs must reference registered assets", "edit_contract.protected_photo_ids")
    if not isinstance(contract["allowed_regions"], list):
        issue("CONTRACT_CONFLICT", "allowed_regions must be an array", "edit_contract.allowed_regions")
    if mode_id in {"A01", "A03", "A06", "A10"} and not request.get("targets"):
        issue("TARGET_AMBIGUOUS", f"Specify the object or person to edit for {mode_id}", "targets")
    if mode_id == "A02" and (options.get("optional_local_edits") or options.get("makeup") or options.get("reshape_face")):
        issue("CONTRACT_CONFLICT", "A02 only adjusts light and color; local retouch needs a separately explicit plan", "mode_options")
    if mode_id == "A11":
        bindings = options.get("object_words")
        if not isinstance(bindings, list) or not bindings:
            issue("TARGET_AMBIGUOUS", "A11 requires object_words bindings for photo, target, word and color", "mode_options.object_words")
        else:
            for binding in bindings:
                if not isinstance(binding, dict) or binding.get("photo_id") not in known or any(not isinstance(binding.get(k), str) or not binding[k].strip() for k in ("target", "word", "color")):
                    issue("TARGET_AMBIGUOUS", "Each object_words item requires a registered photo_id and nonempty target/word/color", "mode_options.object_words")
    try:
        if mode_id == "A07":
            selection = options.get("selected_photo_ids", content_ids)
            _known_references(selection, content_ids, "Select travel photos for stickers")
            if not 2 <= len(selection) <= 15:
                raise HappyTripError("ASSET_COUNT_INVALID", "A07 requires 2–15 selected travel photos")
            plan["stages"] = plan_stickers([a for a in assets if a["photo_id"] in content_ids], selection)
            plan["asset_mapping"] = [{"photo_id": p, "stage_id": s["id"], "source_photo_ids": [p]} for p, s in zip(selection, plan["stages"])]
            omitted = [i for i in content_ids if i not in selection]
            plan["unselected_assets"] = [{"photo_id": i, "reason": "Not included in explicit selected_photo_ids"} for i in omitted]
            if omitted:
                plan["warnings"].append("Some supplied photos were not selected; see unselected_assets")
            if len(suitcase_ids) > 1:
                raise HappyTripError("TARGET_AMBIGUOUS", "Select one suitcase reference")
            if not suitcase_ids:
                plan["stages"].append(_stage("suitcase-base", "generate", [], "Generate an empty open suitcase with clear upper and lower interior liners, no stickers.", unit={"type": "suitcase"}))
        elif mode_id == "B16":
            panels = options.get("panels", [])
            if not isinstance(panels, list) or type(options.get("panel_count")) is not int or options["panel_count"] not in (3, 4) or len(panels) != options["panel_count"]:
                raise HappyTripError("STORY_INVALID", "panel_count must be 3 or 4 and match the structured panels")
            if any(p.get("basis") in {"fiction", "explicit_fiction"} for p in panels if isinstance(p, dict)) and options.get("story_basis") not in {"explicit_fiction", "fiction"}:
                raise HappyTripError("STORY_BASIS_UNKNOWN", "Fictional panels require story_basis=explicit_fiction")
            plan["stages"] = plan_comic(panels, assets)
            plan["asset_mapping"] = [{"panel": s["unit"]["index"], "stage_id": s["id"], "source_photo_ids": s["photo_ids"]} for s in plan["stages"]]
        elif mode_id == "B22":
            map_mode = options.get("map_mode", "itinerary_schematic")
            order = options.get("ordered_stop_ids") if options.get("order_confirmed") is True else None
            route = plan_route(options.get("stops", []), order, map_mode)
            for stop in route["stops"]:
                _known_references(stop["photo_ids"], known, f"Stop {stop['id']} requires photo bindings")
            mapped = {p for stop in route["stops"] for p in stop["photo_ids"]}
            if set(known) - mapped:
                raise HappyTripError("ASSET_MAPPING_MISSING", "Every selected map photo must belong to a stop")
            template = options.get("template", "travel_poster")
            if not isinstance(template, str) or template not in {"travel_poster", "classic"}:
                raise HappyTripError("INPUT_INVALID", "B22 template must be travel_poster or classic")
            if template == "classic" and map_mode == "geographic":
                raise HappyTripError("INPUT_INVALID", "Geographic maps require template=travel_poster")
            if map_mode != "geographic" and (options.get("basemap") or options.get("route_segments")):
                raise HappyTripError("MAP_MODE_INVALID", "Basemap and route geometries require map_mode=geographic")
            route.update({"kind": "route", "template": template})
            for field in ("title", "subtitle", "date_range", "footer", "basemap", "route_segments",
                          "size", "font_path", "title_font_path", "font_size", "background", "map_layout"):
                if field in options:
                    route[field] = deepcopy(options[field])
            validate_route_facts(route)
            plan["route_layout"] = route
            if not route["ordered_stop_ids"] and map_mode != "unordered_places":
                issue("FACT_ORDER_UNKNOWN", "Confirm stop order or explicitly select unordered_places; no route edges were planned", "mode_options.ordered_stop_ids")
            if map_mode == "geographic":
                require("geographic_rendering")
                from .maps import validate_geographic
                geographic = validate_geographic(route, check_files=True)
                route.update({"basemap": geographic["basemap"], "route_segments": geographic["route_segments"]})
            if options.get("show_schematic_label") is False and map_mode != "geographic":
                issue("CONTRACT_CONFLICT", "Conceptual maps require the non-scale schematic label", "mode_options.show_schematic_label")
        elif mode_id != "A12":
            instruction = "Generate an image candidate for the selected mode; preserve the contract and source references."
            if mode_id == "B01":
                instruction = "Generate only the souvenir magnet asset. Do not generate a complete poster or redraw the original-photo region."
            plan["stages"] = [_stage("image-01", "generate", known, instruction)]
    except HappyTripError as exc:
        issue(exc.code, str(exc), "mode_options")
    needs_composition = scope == "hybrid_layout" or mode_id in {"A12", "B16"} or contract.get("strict_original") is True
    has_exact_text = bool(request.get("text") or request.get("texts") or any(request.get("output", {}).get(k) for k in ("title", "subtitle", "text", "date")))
    if has_exact_text or mode_id in {"B16", "B22"}:
        needs_composition = True
        require("exact_text_rendering")
    if needs_composition:
        require("local_composition")
        generation_ids = [s["id"] for s in plan["stages"]]
        plan["stages"].append(_stage("compose", "compose", known,
                                     "Use actual generated unit outputs and registered photo assets. Preserve mappings, apply only authorized regions, and render approved exact text; composition must be explicitly supplied and verified.",
                                     depends_on=generation_ids, unit={"type": "composition", "mode": mode_id}))
    if scope == "masked_edit" and contract.get("strict_original") is not True:
        plan["warnings"].append("Generated local-edit candidates do not prove unchanged background pixels; visual review is required")
    targets = request.get("targets", [])
    targets = targets if isinstance(targets, list) else []
    if scope == "masked_edit" and contract.get("strict_original") is True and not contract.get("allowed_regions") and not request.get("masks") and not any(isinstance(t, dict) and (t.get("mask") or t.get("bbox")) for t in targets):
        plan["warnings"].append("An effective edit mask must be established before composition and pixel-protection validation")
    if plan["stages"]:
        plan["stages"].append(_stage("validate", "validate", known,
                                     "Review actual output against the mode checklist, fact ledger, source mappings and edit contract. Never mark a candidate as visually accepted automatically.",
                                     depends_on=[plan["stages"][-1]["id"]], unit={"type": "validation"}))
    generation = [s for s in plan["stages"] if s["kind"] == "generate"]
    if generation:
        require("image_generation")
    if mode_id == "A07" and generation:
        require("transparent_assets")
    if any(s["photo_ids"] for s in generation):
        require("image_editing")
    if any(len(s["photo_ids"]) > 1 for s in generation):
        require("multiple_references")
        limit = caps.get("max_reference_images")
        if type(limit) is not int or limit < 1:
            plan["missing_capabilities"].append({"capability": "max_reference_images", "available": limit or "unknown"})
            plan["required_capabilities"].append("max_reference_images")
        elif any(len(s["photo_ids"]) > limit for s in generation):
            issue("CAPABILITY_MISSING", f"A generation unit exceeds max_reference_images={limit}; explicitly select valid reference bindings or a supported provider")
    plan["estimated_image_calls"] = sum(s["image_calls"] for s in plan["stages"])
    plan["estimated_max_with_repairs"] = plan["estimated_image_calls"] * (1 + plan["call_budget"]["max_repairs_per_stage"])
    if plan["estimated_image_calls"] > plan["call_budget"]["max_image_calls"]:
        issue("BUDGET_EXCEEDED", f"Plan needs {plan['estimated_image_calls']} image calls; authorized budget is {plan['call_budget']['max_image_calls']}", "budget.max_image_calls")
    elif plan["estimated_max_with_repairs"] > plan["call_budget"]["max_image_calls"]:
        plan["warnings"].append("The authorized budget does not reserve every potential repair; execution must stop before any extra call")
    generation_missing = any(c["capability"] == "image_generation" for c in plan["missing_capabilities"])
    # A pure prompt handoff needs no live editor. Other missing constraints such
    # as strict-original composition still retain their blocking state.
    prompt_capabilities = {"image_generation", "image_editing", "multiple_references", "max_reference_images", "transparent_assets"} if generation_missing else {"image_generation"}
    missing_other = [c for c in plan["missing_capabilities"] if c["capability"] not in prompt_capabilities]
    if any(e["code"] != "CAPABILITY_MISSING" for e in plan["errors"]):
        plan["status"] = "needs_input"
    elif missing_other or any(e["code"] == "CAPABILITY_MISSING" for e in plan["errors"]):
        plan["status"] = "needs_capability"
    elif any(c["capability"] == "image_generation" for c in plan["missing_capabilities"]):
        plan["status"] = "prompt_only"
    if plan["missing_capabilities"]:
        plan["errors"].append({"code": "CAPABILITY_MISSING", "message": "Unconfirmed or unavailable capabilities: " + ", ".join(c["capability"] for c in plan["missing_capabilities"])})
    return plan
