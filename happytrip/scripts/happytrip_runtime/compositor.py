"""Explicit deterministic PNG recipes. This module never calls a generator."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .assets import load_normalized_image, local_path, sha256_file, validate_box, validate_mask
from .types import HappyTripError


def _path(value):
    return local_path(value.get("working_path", value.get("path", value.get("ref")))) if isinstance(value, dict) else local_path(value)


def _source_asset(asset):
    if not isinstance(asset, dict) or not all(asset.get(key) for key in ("photo_id", "ref", "working_path", "input_sha256", "working_sha256")):
        raise HappyTripError("PROVENANCE_INVALID", "Photo slots require a registered source Asset with both hashes.")
    original, working = local_path(asset["ref"]), local_path(asset["working_path"])
    if sha256_file(original) != asset["input_sha256"] or sha256_file(working) != asset["working_sha256"]:
        raise HappyTripError("PROVENANCE_INVALID", f"Source or workcopy changed: {asset['photo_id']}")
    image, source = load_normalized_image(working), load_normalized_image(original)
    if image.size != source.size or image.mode != source.mode or any(high > 0 for low, high in ImageChops.difference(image, source).getextrema()):
        image.close()
        source.close()
        raise HappyTripError("PROVENANCE_INVALID", "Photo slot workcopy must be the deterministic normalized original.")
    source.close()
    return image, {"photo_id": asset["photo_id"], "input_sha256": asset["input_sha256"], "working_sha256": asset["working_sha256"], "source_kind": "registered_original"}


def _rect(box, size):
    x, y, width, height = validate_box(box)
    result = (round(x * size[0]), round(y * size[1]), round((x + width) * size[0]), round((y + height) * size[1]))
    if result[2] <= result[0] or result[3] <= result[1]:
        raise HappyTripError("REGION_INVALID", "Region must cover at least one pixel in each dimension.")
    return result


def _region_mask(regions, size):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        box = region.get("box") if isinstance(region, dict) else region
        if box is None:
            raise HappyTripError("TARGET_AMBIGUOUS", "Pixel protection needs a concrete box or mask, not a description alone.")
        left, top, right, bottom = _rect(box, size)
        draw.rectangle((left, top, right - 1, bottom - 1), fill=255)
    return mask


def _check_permission(mask, contract):
    if contract.get("allowed_regions"):
        allowed = _region_mask(contract["allowed_regions"], mask.size)
        outside = ImageChops.multiply(mask, ImageChops.invert(allowed))
        if outside.getbbox():
            raise HappyTripError("CONTRACT_CONFLICT", "Effective mask exceeds allowed regions, including feathering and shadows.")
    protected = contract.get("protected_regions", [])
    if protected and ImageChops.multiply(mask, _region_mask(protected, mask.size)).getbbox():
        raise HappyTripError("CONTRACT_CONFLICT", "Effective editing mask overlaps a protected region.")


def verify_protected_pixels(before, after, effective_mask):
    """Compare decoded normalized RGBA pixels only where mask is exactly zero."""
    original, result = load_normalized_image(_path(before)), load_normalized_image(_path(after))
    if original.size != result.size:
        original.close()
        result.close()
        return {"status": "fail", "reason": "Canvas dimensions differ.", "changed_pixels": None}
    mask = validate_mask(effective_mask, original.size)
    original, result = original.convert("RGBA"), result.convert("RGBA")
    difference = ImageChops.difference(original, result)
    channels = difference.split()
    changed_mask = channels[0]
    for channel in channels[1:]:
        changed_mask = ImageChops.lighter(changed_mask, channel)
    changed_mask = ImageChops.multiply(changed_mask.point(lambda value: 255 if value else 0), mask.point(lambda value: 0 if value else 255))
    changed = changed_mask.histogram()[255]
    original.close()
    result.close()
    mask.close()
    return {"status": "pass" if changed == 0 else "fail", "reason": "Pixels outside the effective mask are identical." if changed == 0 else "Protected pixels changed.", "changed_pixels": changed}


def _font(path, size, text):
    if not path:
        raise HappyTripError("FONT_MISSING", "Supply a real font_path for exact text; no fallback font is assumed.")
    try:
        font = ImageFont.truetype(str(local_path(path)), size=int(size))
    except (OSError, ValueError) as exc:
        raise HappyTripError("FONT_MISSING", "Font cannot be loaded.") from exc
    missing = bytes(font.getmask("\U0010ffff"))
    for char in set(text):
        if not char.isspace() and bytes(font.getmask(char)) == missing:
            raise HappyTripError("FONT_GLYPH_MISSING", f"Selected font lacks glyph U+{ord(char):04X}.")
    return font


def _text(canvas, spec):
    text = spec.get("text")
    if not isinstance(text, str) or not text:
        raise HappyTripError("TEXT_INVALID", "An exact nonempty text string is required.")
    font = _font(spec.get("font_path"), spec.get("font_size", 28), text)
    rectangle = _rect(spec["box"], canvas.size)
    draw = ImageDraw.Draw(canvas)
    bounds = draw.multiline_textbbox((0, 0), text, font=font, spacing=spec.get("spacing", 4))
    if bounds[2] - bounds[0] > rectangle[2] - rectangle[0] or bounds[3] - bounds[1] > rectangle[3] - rectangle[1]:
        raise HappyTripError("TEXT_OVERFLOW", "Exact text does not fit its box; increase the box or explicitly reduce font_size.")
    draw.multiline_text((rectangle[0] - bounds[0], rectangle[1] - bounds[1]), text, fill=spec.get("color", "#202020"), font=font, spacing=spec.get("spacing", 4))
    return {"kind": "exact_text", "text": text, "font_path": str(Path(spec["font_path"]).resolve()), "box": list(spec["box"])}


def _contain(canvas, image, box, strict_pixels=False):
    left, top, right, bottom = _rect(box, canvas.size)
    if strict_pixels:
        if image.width > right - left or image.height > bottom - top:
            raise HappyTripError("CONTRACT_CONFLICT", "Photo slot cannot hold original pixels; enlarge the canvas or photo slot.")
        width, height = image.size
    else:
        scale = min((right - left) / image.width, (bottom - top) / image.height)
        width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    x, y = left + (right - left - width) // 2, top + (bottom - top - height) // 2
    inserted = image.convert("RGBA")
    if inserted.size != (width, height):
        inserted = inserted.resize((width, height), Image.Resampling.LANCZOS)
    if strict_pixels:
        canvas.paste(inserted, (x, y))
    else:
        canvas.alpha_composite(inserted, (x, y))
    return {"fit": "original_pixels" if strict_pixels else "contain", "source_size": list(image.size), "placed_box_px": [x, y, width, height], "scale": [width / image.width, height / image.height], "slot_box": list(box)}


def _output(layout, sources):
    if not layout.get("output_path"):
        raise HappyTripError("OUTPUT_INVALID", "layout.output_path is required.")
    output = Path(layout["output_path"]).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise HappyTripError("OUTPUT_INVALID", "Composition master must be a lossless PNG.")
    if output.exists() or output in {Path(source).resolve() for source in sources}:
        raise HappyTripError("OUTPUT_INVALID", "Output must be a new file and must not overwrite any source or symlink target.")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _route(canvas, assets, layout, provenance):
    if layout.get("map_mode") == "unordered_places":
        layout = {**layout, "map_mode": "collection"}
    if layout.get("map_mode", "itinerary_schematic") not in {"itinerary_schematic", "collection"}:
        raise HappyTripError("CAPABILITY_MISSING", "This compositor only draws labeled conceptual itineraries, not geographic maps.")
    stops = layout.get("stops", [])
    if not isinstance(stops, list) or not 2 <= len(stops) <= 15:
        raise HappyTripError("INPUT_INVALID", "Route layout requires 2–15 stops.")
    ids = [stop.get("id") for stop in stops]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != len(ids):
        raise HappyTripError("INPUT_INVALID", "Stops need distinct IDs; same names must not be merged.")
    order = layout.get("ordered_stop_ids", [])
    confirmed = layout.get("order_confirmed") is True
    if layout.get("map_mode") == "collection":
        order, confirmed = [], False
    if confirmed and (len(order) != len(ids) or set(order) != set(ids)):
        raise HappyTripError("FACT_ORDER_UNKNOWN", "Confirmed order must contain every stop exactly once.")
    by_stop = dict(zip(ids, stops))
    arranged = [by_stop[sid] for sid in order] if confirmed else stops
    by_photo = {asset["photo_id"]: asset for asset in assets}
    selected = set(by_photo)
    mapped = set()
    for stop in stops:
        photo_ids = stop.get("photo_ids", [])
        if not isinstance(stop.get("name"), str) or not stop["name"] or not isinstance(photo_ids, list) or not photo_ids:
            raise HappyTripError("INPUT_INVALID", "Each stop requires an exact name and photo_ids.")
        if any(pid not in by_photo for pid in photo_ids):
            raise HappyTripError("ASSET_MISSING", "A route photo mapping references an unregistered photo.")
        mapped.update(photo_ids)
    if mapped != selected:
        raise HappyTripError("ASSET_MISSING", "Every selected route photo must be mapped to a stop.")
    columns = 2 if len(stops) > 3 else 1
    rows = math.ceil(len(stops) / columns)
    cell_w, cell_h = 0.90 / columns, 0.82 / rows
    positions = [(0.05 + (i % columns) * cell_w, 0.14 + (i // columns) * cell_h) for i in range(len(stops))]
    edges = []
    if confirmed and layout.get("map_mode") != "collection":
        draw = ImageDraw.Draw(canvas)
        points = [(round((x + cell_w / 2) * canvas.width), round((y + 0.015) * canvas.height)) for x, y in positions]
        for index, (first, second) in enumerate(zip(points, points[1:])):
            draw.line((first, second), fill="#71867f", width=3)
            angle = math.atan2(second[1] - first[1], second[0] - first[0])
            arrow = [second, (second[0] - 12 * math.cos(angle - .45), second[1] - 12 * math.sin(angle - .45)), (second[0] - 12 * math.cos(angle + .45), second[1] - 12 * math.sin(angle + .45))]
            draw.polygon(arrow, fill="#71867f")
            edges.append([order[index], order[index + 1]])
    label = "行程示意，非比例地图" if confirmed and edges else "地点集（顺序未确认）"
    if layout.get("map_mode") == "collection" and confirmed:
        label = "地点照片集（非比例地图）"
    font_path = layout.get("font_path")
    font_size = layout.get("font_size", 24)
    provenance.append(_text(canvas, {"text": label, "font_path": font_path, "font_size": font_size, "box": [.05, .035, .90, .07]}))
    for index, (stop, (x, y)) in enumerate(zip(arranged, positions)):
        name = (f"{index + 1}. " if edges else "") + stop["name"]
        provenance.append(_text(canvas, {"text": name, "font_path": font_path, "font_size": font_size, "box": [x, y, cell_w - .02, cell_h * .20]}))
        width = (cell_w - .025) / len(stop["photo_ids"])
        for photo_index, pid in enumerate(stop["photo_ids"]):
            image, record = _source_asset(by_photo[pid])
            box = [x + photo_index * width, y + cell_h * .22, width - .01, cell_h * .66]
            record.update(_contain(canvas, image, box))
            record.update({"kind": "source_photo", "stop_id": stop["id"], "stop_name": stop["name"]})
            provenance.append(record)
            image.close()
    return {"ordered_stop_ids": order if confirmed else [], "order_confirmed": confirmed, "edges": edges, "label": label, "map_mode": "itinerary_schematic" if edges else "collection"}


def compose(base, layers, layout, contract):
    """Create a new PNG from an explicit JSON recipe and return provenance.

    ``layout.kind``: masked_edit, overlay, collage, canvas, poster/B01, or route/B22.
    ``base``: registered Asset, local path (local edits only), or Asset list (route).
    Layer kinds: image {path, box}, photo {asset, box}, text {text, box,
    font_path, font_size}. Masked edit uses one {path, mask_path} layer.
    Boxes are normalized [x,y,w,h]. layout.output_path is always required.
    """
    if not isinstance(layout, dict) or not isinstance(contract, dict) or not isinstance(layers, list):
        raise HappyTripError("INPUT_INVALID", "Composition requires layout/contract objects and a layers list.")
    kind = layout.get("kind", "overlay")
    kind = {"B01": "poster", "B22": "route"}.get(kind, kind)
    if kind not in {"masked_edit", "overlay", "collage", "canvas", "poster", "route"}:
        raise HappyTripError("INPUT_INVALID", f"Unsupported compositor recipe: {kind}")
    sources = []
    bases = base if isinstance(base, list) else [base]
    for asset in bases:
        if asset is not None:
            sources.append(_path(asset))
            if isinstance(asset, dict) and asset.get("ref"):
                sources.append(asset["ref"])
    sources.extend(layer["path"] for layer in layers if layer.get("path"))
    output = _output(layout, sources)
    provenance, checks, route_info = [], [], None
    local_kinds = {"masked_edit", "overlay", "collage"}
    if kind in local_kinds:
        if isinstance(base, dict):
            for group in ("allowed_regions", "protected_regions"):
                if any(isinstance(region, dict) and region.get("photo_id", base.get("photo_id")) != base.get("photo_id") for region in contract.get(group, [])):
                    raise HappyTripError("CONTRACT_CONFLICT", "Local-edit region bindings must reference the base photo.")
        if isinstance(base, dict) and base.get("input_sha256"):
            canvas, base_record = _source_asset(base)
            canvas = canvas.convert("RGBA")
            base_record["kind"] = "base"
        else:
            canvas = load_normalized_image(_path(base)).convert("RGBA")
            base_record = {"kind": "base", "source_kind": "supplied_base", "sha256": sha256_file(_path(base))}
        provenance.append(base_record)
        base_size = canvas.size
        if layout.get("size") and tuple(layout["size"]) != base_size:
            raise HappyTripError("CONTRACT_CONFLICT", "Local edits must retain the normalized source canvas dimensions.")
        if kind == "masked_edit":
            if len(layers) != 1 or not layers[0].get("mask_path"):
                raise HappyTripError("MASK_INVALID", "Masked edit requires one candidate layer and an explicit effective mask_path.")
            candidate = load_normalized_image(local_path(layers[0]["path"])).convert("RGBA")
            if candidate.size != canvas.size:
                raise HappyTripError("CONTRACT_CONFLICT", "Candidate and base must have identical normalized dimensions.")
            mask = validate_mask(layers[0]["mask_path"], canvas.size)
            _check_permission(mask, contract)
            canvas = Image.composite(candidate, canvas, mask)
            provenance.append({"kind": "masked_edit", "effective_mask_sha256": sha256_file(layers[0]["mask_path"]), "candidate_sha256": sha256_file(layers[0]["path"])})
            candidate.close()
        else:
            interior_regions = layout.get("interior_regions", [])
            if kind == "collage":
                if len(interior_regions) != 2:
                    raise HappyTripError("INPUT_INVALID", "Suitcase collage requires exactly two explicit interior_regions.")
                interior_rectangles = [_rect(region.get("box") if isinstance(region, dict) else region, canvas.size) for region in interior_regions]
                mapped = set()
                for layer in layers:
                    if layer.get("kind", "image") == "image":
                        source_ids = layer.get("source_photo_ids")
                        if not isinstance(source_ids, list) or not source_ids or any(not isinstance(pid, str) or not pid for pid in source_ids):
                            raise HappyTripError("PROVENANCE_INVALID", "Every suitcase sticker requires source_photo_ids.")
                        mapped.update(source_ids)
                    rect = _rect(layer.get("box", [0, 0, 1, 1]), canvas.size)
                    if not any(rect[0] >= box[0] and rect[1] >= box[1] and rect[2] <= box[2] and rect[3] <= box[3] for box in interior_rectangles):
                        raise HappyTripError("CONTRACT_CONFLICT", "Each suitcase layer must fit completely inside one declared interior region.")
                if layout.get("selected_photo_ids") and mapped != set(layout["selected_photo_ids"]):
                    raise HappyTripError("ASSET_MISSING", "Selected suitcase photos and sticker source mappings must match.")
            overlay = Image.new("RGBA", canvas.size)
            for layer in layers:
                if layer.get("kind", "image") == "text":
                    text_layer = Image.new("RGBA", canvas.size)
                    record = _text(text_layer, layer)
                    _check_permission(text_layer.getchannel("A"), contract)
                    overlay.alpha_composite(text_layer)
                    provenance.append(record)
                    text_layer.close()
                elif layer.get("kind", "image") == "image":
                    image = load_normalized_image(local_path(layer["path"]))
                    record = {"kind": "overlay", "sha256": sha256_file(layer["path"]), "source_photo_ids": layer.get("source_photo_ids", [])}
                    record.update(_contain(overlay, image, layer.get("box", [0, 0, 1, 1])))
                    provenance.append(record)
                    image.close()
                else:
                    raise HappyTripError("INPUT_INVALID", "Overlay layers must be image or text.")
            alpha = overlay.getchannel("A")
            if contract.get("allowed_regions"):
                alpha = ImageChops.multiply(alpha, _region_mask(contract["allowed_regions"], canvas.size))
            if kind == "collage":
                alpha = ImageChops.multiply(alpha, _region_mask(interior_regions, canvas.size))
            if contract.get("protected_regions"):
                alpha = ImageChops.multiply(alpha, ImageChops.invert(_region_mask(contract["protected_regions"], canvas.size)))
            overlay.putalpha(alpha)
            mask = alpha
            canvas = Image.alpha_composite(canvas, overlay)
            overlay.close()
        mask_output = output.with_name(output.stem + "-effective-mask.png")
        if mask_output.exists() or mask_output.resolve() in {Path(source).resolve() for source in sources}:
            raise HappyTripError("OUTPUT_INVALID", "Effective-mask output must also be a new file.")
        with mask_output.open("xb") as stream:
            mask.save(stream, format="PNG")
        mask.close()
    else:
        size = layout.get("size", [1200, 1600])
        if not isinstance(size, (list, tuple)) or len(size) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in size) or size[0] * size[1] > 50_000_000:
            raise HappyTripError("OUTPUT_INVALID", "Canvas size must be positive integer dimensions under 50 megapixels.")
        canvas = Image.new("RGBA", tuple(size), layout.get("background", "#f6f0e4"))
        if kind == "route":
            if layers:
                raise HappyTripError("INPUT_INVALID", "Route recipe uses explicit stops; arbitrary layers are not supported.")
            template = layout.get("template", "travel_poster")
            if template == "classic":
                route_info = _route(canvas, bases, layout, provenance)
            elif template == "travel_poster":
                from .route_poster import render_travel_poster
                route_info = render_travel_poster(canvas, bases, layout, contract, provenance)
            else:
                raise HappyTripError("INPUT_INVALID", "B22 template must be travel_poster or classic.")
        else:
            photo_box = layout.get("photo_box", [.08, .54, .84, .40])
            if kind == "poster" and not any(layer.get("kind", "image") == "image" for layer in layers):
                raise HappyTripError("ASSET_MISSING", "B01 needs a generated souvenir image layer in addition to the source photo.")
            photo_rectangle = _rect(photo_box, canvas.size)
            for layer in layers:
                if kind == "poster" and _overlap(_rect(layer["box"], canvas.size), photo_rectangle):
                    raise HappyTripError("CONTRACT_CONFLICT", "Poster layers must not overlap the reserved original-photo slot.")
                layer_kind = layer.get("kind", "image")
                if layer_kind == "text":
                    provenance.append(_text(canvas, layer))
                elif layer_kind in {"image", "photo"}:
                    if layer_kind == "photo":
                        image, record = _source_asset(layer["asset"])
                        record["kind"] = "source_photo"
                    else:
                        image = load_normalized_image(local_path(layer["path"]))
                        record = {"kind": "generated_layer", "sha256": sha256_file(layer["path"]), "source_photo_ids": layer.get("source_photo_ids", [])}
                    record.update(_contain(canvas, image, layer["box"]))
                    provenance.append(record)
                    image.close()
                else:
                    raise HappyTripError("INPUT_INVALID", f"Unsupported layer kind: {layer_kind}")
            if kind == "poster":
                image, record = _source_asset(base)
                strict = contract.get("original_pixels") is True or layout.get("original_pixels") is True
                record.update(_contain(canvas, image, photo_box, strict_pixels=strict))
                record["kind"] = "source_photo"
                provenance.append(record)
                image.close()
    with output.open("xb") as stream:
        canvas.save(stream, format="PNG")
    dimensions = list(canvas.size)
    canvas.close()
    if kind in local_kinds:
        checks.append({"name": "protected_pixels", **verify_protected_pixels(base, output, mask_output)})
    else:
        checks.append({"name": "source_provenance", "status": "pass", "reason": "Every source-photo slot was verified against its registered original."})
    digest = sha256_file(output)
    result = {"status": "candidate", "path": str(output), "format": "PNG", "size": dimensions, "sha256": digest, "output_sha256": digest, "provenance": provenance, "checks": checks,
              "validation": {"status": "pass" if all(check["status"] == "pass" for check in checks) else "fail", "checks": checks}, "visual_review": "not_run"}
    if kind in local_kinds:
        result["effective_mask_path"] = str(mask_output)
    if route_info is not None:
        result["route"] = route_info
    return result
