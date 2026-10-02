"""Deterministic B22 travel poster: original photographs and sourced geography.

No map, date, distance or travel order is inferred here. Raster basemaps and
route geometries are validated by maps.py; schematic coordinates are decorative.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .types import HappyTripError

INK = "#263331"
MUTED = "#6d7973"
RED = "#b74734"
PAPER = "#f5f1e7"


def _wrap(draw, text, font, width):
    """Wrap without deleting, abbreviating or replacing any input characters."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for character in paragraph:
            if line and draw.textlength(line + character, font=font) > width:
                lines.append(line)
                line = character
            else:
                line += character
        lines.append(line)
    return "\n".join(lines)


def _fitted_text(canvas, text, box, font_path, desired, minimum, provenance,
                 color=INK, align="left", name="text", wrap=True):
    from .compositor import _font
    if not isinstance(text, str) or not text:
        raise HappyTripError("TEXT_INVALID", f"{name} must be a nonempty text string.")
    x, y, width, height = [int(round(value)) for value in box]
    if width < 1 or height < 1:
        raise HappyTripError("TEXT_OVERFLOW", f"No space for {name}; enlarge the poster.")
    draw = ImageDraw.Draw(canvas)
    for size in range(max(int(desired), int(minimum)), max(1, int(minimum)) - 1, -1):
        font = _font(font_path, size, text)
        rendered = _wrap(draw, text, font, width) if wrap else text
        spacing = max(2, round(size * .18))
        bounds = draw.multiline_textbbox((0, 0), rendered, font=font, spacing=spacing, align=align)
        if bounds[2] - bounds[0] <= width and bounds[3] - bounds[1] <= height:
            x_offset = (width - (bounds[2] - bounds[0])) / 2 if align == "center" else 0
            draw.multiline_text((x + x_offset - bounds[0], y - bounds[1]), rendered,
                                font=font, fill=color, spacing=spacing, align=align)
            provenance.append({"kind": "exact_text", "text": text, "rendered_text": rendered,
                               "font_path": str(Path(font_path).resolve()), "font_size": size,
                               "box_px": [x, y, width, height], "field": name})
            return size
    raise HappyTripError("TEXT_OVERFLOW", f"Exact {name} does not fit even at {minimum}px. Enlarge layout.size or supply a shorter approved text; text was not truncated.")


def _dashed(draw, points, fill, width, dash):
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        for offset in range(0, math.ceil(length), max(2, dash * 2)):
            until = min(length, offset + dash)
            draw.line([(start[0] + dx * offset / length, start[1] + dy * offset / length),
                       (start[0] + dx * until / length, start[1] + dy * until / length)], fill=fill, width=width)


def _shadow_paste(canvas, card, xy, angle, scale):
    rotated = card.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    radius = max(2, round(scale * 8))
    shadow = Image.new("RGBA", rotated.size, (32, 43, 40, 0))
    shadow.putalpha(rotated.getchannel("A").point(lambda value: round(value * .20)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius))
    x, y = round(xy[0] - (rotated.width - card.width) / 2), round(xy[1] - (rotated.height - card.height) / 2)
    if x < 0 or y < 0 or x + rotated.width > canvas.width or y + rotated.height > canvas.height:
        raise HappyTripError("LAYOUT_OVERFLOW", "Rotated photo frame would leave the canvas; enlarge the canvas.")
    canvas.alpha_composite(shadow, (x + round(3 * scale), y + round(7 * scale)))
    canvas.alpha_composite(rotated, (x, y))
    return {"rotation_degrees": angle, "frame_origin_px": [x, y], "frame_size_px": list(rotated.size)}


def _floating_card_positions(size, card_size, target_ids, anchors, pin_centers, clearance):
    """Choose perimeter cards without hiding a projected stop or another card."""
    width, height = size
    card_w, card_h = card_size
    margin = max(7, round(clearance * .45))
    if card_w + margin * 2 > width or card_h + margin * 2 > height:
        raise HappyTripError("LAYOUT_OVERFLOW", "Floating photo cards cannot fit the map; use map_layout='split' or a larger canvas.")
    xs = [margin, (width - card_w) // 2, width - card_w - margin]
    ys = [round(margin + fraction * (height - card_h - 2 * margin)) for fraction in (0, .25, .5, .75, 1)]
    candidates = [(x, y, card_w, card_h) for x in (xs[0], xs[2]) for y in ys]
    candidates += [(xs[1], ys[0], card_w, card_h), (xs[1], ys[-1], card_w, card_h)]

    def covers(rect, point):
        x, y, w, h = rect
        return x - clearance <= point[0] <= x + w + clearance and y - clearance <= point[1] <= y + h + clearance

    def intersects(a, b):
        return a[0] < b[0] + b[2] + margin and a[0] + a[2] + margin > b[0] and a[1] < b[1] + b[3] + margin and a[1] + a[3] + margin > b[1]

    points = list(anchors.values()) + list(pin_centers)
    candidates = [rect for rect in candidates if not any(covers(rect, point) for point in points)]
    options = []
    for sid in target_ids:
        anchor = anchors[sid]
        options.append(sorted(candidates, key=lambda rect: math.hypot(rect[0] + rect[2] / 2 - anchor[0], rect[1] + rect[3] / 2 - anchor[1])))
    best, best_cost = None, math.inf

    def search(index, chosen, cost):
        nonlocal best, best_cost
        if cost >= best_cost:
            return
        if index == len(options):
            best, best_cost = list(chosen), cost
            return
        for rect in options[index]:
            if any(intersects(rect, other) for other in chosen):
                continue
            anchor = anchors[target_ids[index]]
            increment = math.hypot(rect[0] + rect[2] / 2 - anchor[0], rect[1] + rect[3] / 2 - anchor[1])
            search(index + 1, chosen + [rect], cost + increment)

    search(0, [], 0)
    if best is None:
        raise HappyTripError("LAYOUT_OVERFLOW", "Map pins leave no readable space for floating photo cards. Use map_layout='split' or expand the map extent; no photo was omitted.")
    return best


def _schema(assets, layout, contract):
    from .planner import validate_route_facts
    validate_route_facts(layout)
    if contract.get("original_pixels") is True or layout.get("original_pixels") is True:
        raise HappyTripError("CONTRACT_CONFLICT", "travel_poster scales and rotates photos. Original-pixel preservation requires a separate unscaled canvas recipe.")
    if not 2 <= len(assets) <= 15 or any(not isinstance(asset, dict) for asset in assets):
        raise HappyTripError("ASSET_MISSING", "B22 requires 2–15 registered original photo Assets.")
    photo_ids = [asset.get("photo_id") for asset in assets]
    if any(not isinstance(pid, str) or not pid for pid in photo_ids) or len(set(photo_ids)) != len(photo_ids):
        raise HappyTripError("ASSET_INVALID", "B22 photo IDs must be unique.")
    stops = layout.get("stops", [])
    if not isinstance(stops, list) or not 2 <= len(stops) <= 15 or any(not isinstance(stop, dict) for stop in stops):
        raise HappyTripError("INPUT_INVALID", "B22 requires 2–15 named stops.")
    ids = [stop.get("id") for stop in stops]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != len(ids):
        raise HappyTripError("INPUT_INVALID", "Stops require distinct nonempty IDs.")
    mapped = set()
    for stop in stops:
        bindings = stop.get("photo_ids")
        if not isinstance(stop.get("name"), str) or not stop["name"] or not isinstance(bindings, list) or not bindings:
            raise HappyTripError("INPUT_INVALID", "Each stop needs an exact name and photo_ids.")
        if any(not isinstance(pid, str) or pid not in photo_ids for pid in bindings) or len(set(bindings)) != len(bindings):
            raise HappyTripError("ASSET_MISSING", "Stop photo bindings must use distinct registered photo IDs.")
        mapped.update(bindings)
    if mapped != set(photo_ids):
        raise HappyTripError("ASSET_MISSING", "Every selected photo must be mapped to a stop.")
    mode = layout.get("map_mode", "itinerary_schematic")
    if not isinstance(mode, str) or mode not in {"itinerary_schematic", "collection", "unordered_places", "geographic"}:
        raise HappyTripError("MAP_MODE_INVALID", f"Unsupported map mode: {mode}")
    if mode != "geographic" and (layout.get("basemap") or layout.get("route_segments")):
        raise HappyTripError("MAP_MODE_INVALID", "Basemap and route geometries require map_mode=geographic; geographic data cannot be silently discarded.")
    map_layout = layout.get("map_layout", "full_map" if mode == "geographic" else "split")
    if not isinstance(map_layout, str) or map_layout not in {"full_map", "split"}:
        raise HappyTripError("MAP_LAYOUT_INVALID", "map_layout must be full_map or split.")
    if map_layout == "full_map" and mode != "geographic":
        raise HappyTripError("MAP_LAYOUT_INVALID", "full_map requires geographic mode and a sourced basemap; a schematic cannot substitute for a real map.")
    confirmed = layout.get("order_confirmed") is True and mode not in {"collection", "unordered_places"}
    order = layout.get("ordered_stop_ids", []) if confirmed else []
    if not isinstance(order, list) or any(not isinstance(sid, str) for sid in order) or (confirmed and (len(order) != len(ids) or set(order) != set(ids))):
        raise HappyTripError("FACT_ORDER_UNKNOWN", "Confirmed order must contain every stop exactly once.")
    by_id = {stop["id"]: stop for stop in stops}
    arranged = [by_id[sid] for sid in order] if confirmed else stops
    return arranged, order, mode


def render_travel_poster(canvas, assets, layout, contract, provenance):
    """Paint onto RGBA canvas and append exact source/text/map provenance."""
    from .compositor import _contain, _source_asset, _font
    stops, order, map_mode = _schema(assets, layout, contract)
    width, height = canvas.size
    if width < 600 or height < 800:
        raise HappyTripError("OUTPUT_INVALID", "Travel poster needs at least 600×800 pixels for readable source labels.")
    scale = width / 1200
    font_path = layout.get("font_path")
    title_font = layout.get("title_font_path", font_path)
    min_font = max(10, round(13 * scale))
    _font(font_path, min_font, "旅途照片行程示意非比例地图")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, width, height), fill=layout.get("background", PAPER))
    # An understated printed border and rule give the page a deliberate hierarchy.
    inset = round(width * .025)
    draw.rounded_rectangle((inset, inset, width - inset, height - inset), radius=round(12 * scale), outline="#d9d4c8", width=max(1, round(scale)))
    draw.line((width * .052, height * .137, width * .948, height * .137), fill="#d3cab9", width=max(1, round(2 * scale)))
    _fitted_text(canvas, "TRAVEL JOURNAL", (width * .052, height * .026, width * .45, height * .020), font_path, 15 * scale, min_font, provenance, color=MUTED, name="eyebrow")
    title = layout.get("title") or "旅途记忆"
    date = layout.get("date_range", {}).get("value") if isinstance(layout.get("date_range"), dict) else None
    title_width = .66 if date else .896
    _fitted_text(canvas, title, (width * .052, height * .052, width * title_width, height * .052), title_font, 67 * scale, max(18, round(28 * scale)), provenance, name="title")
    if date:
        _fitted_text(canvas, str(date), (width * .755, height * .058, width * .19, height * .053), font_path, 21 * scale, min_font, provenance, color=MUTED, name="date_range")
    if layout.get("subtitle"):
        _fitted_text(canvas, layout["subtitle"], (width * .054, height * .111, width * .892, height * .021), font_path, 22 * scale, min_font, provenance, color=MUTED, name="subtitle")

    source_images, source_records = {}, {}
    by_asset = {asset["photo_id"]: asset for asset in assets}
    bindings = [(stop, photo_id) for stop in stops for photo_id in stop["photo_ids"]]
    indices = {stop["id"]: index + 1 for index, stop in enumerate(stops)}
    requested_map_layout = layout.get("map_layout", "full_map" if map_mode == "geographic" else "split")
    actual_map_layout = requested_map_layout
    fallback_reason = None
    if requested_map_layout == "full_map" and len(bindings) > 4:
        actual_map_layout = "split"
        fallback_reason = "More than four stop-photo bindings; split layout retains every original photo and a readable geographic map."
    full_map = actual_map_layout == "full_map"

    def place_photo(card, stop, pid, box, occurrence):
        if pid not in source_images:
            source_images[pid], source_records[pid] = _source_asset(by_asset[pid])
        transform = _contain(card, source_images[pid], box)
        key = (stop["id"], pid)
        record = next((record for record in provenance if record.get("kind") == "source_photo" and (record.get("stop_id"), record.get("photo_id")) == key), None)
        if record is None:
            record = {**source_records[pid], **transform, "kind": "source_photo", "stop_id": stop["id"], "stop_name": stop["name"], "placements": []}
            provenance.append(record)
        placement = {**transform, "occurrence": occurrence}
        record["placements"].append(placement)
        return placement

    try:
        # Header contains 2–3 distinct originals, rather than silently selecting
        # only the first stop's pictures when one stop has several attachments.
        hero_bindings, seen = [], set()
        for stop, pid in bindings:
            if pid not in seen:
                hero_bindings.append((stop, pid))
                seen.add(pid)
            if len(hero_bindings) == 3:
                break
        card_w = round(width * (.285 if len(hero_bindings) == 3 else .365))
        maximum_card_h = round(height * .268)
        angles = [-4, 1, 4] if len(hero_bindings) == 3 else [-3, 3]
        gap = width * .019
        left = (width - len(hero_bindings) * card_w - (len(hero_bindings) - 1) * gap) / 2
        header_bottom = height * .162
        for i, (stop, pid) in enumerate(hero_bindings):
            if pid not in source_images:
                source_images[pid], source_records[pid] = _source_asset(by_asset[pid])
            margin = max(6, round(card_w * .04))
            caption_h = max(29, round(48 * scale))
            photo_h = min(maximum_card_h - caption_h - margin * 2,
                          round((card_w - margin * 2) * source_images[pid].height / source_images[pid].width))
            card_h = photo_h + caption_h + margin * 2
            card = Image.new("RGBA", (card_w, card_h), "#fffdf7")
            placement = place_photo(card, stop, pid, [margin / card_w, margin / card_h, (card_w - margin * 2) / card_w, photo_h / card_h], "header")
            caption = stop["name"]
            if stop.get("date"):
                caption += " · " + str(stop["date"]["value"])
            _fitted_text(card, caption, (card_w * .065, photo_h + margin * 1.5, card_w * .87, caption_h - margin * .3), font_path, 24 * scale, min_font, provenance, align="center", name=f"photo_caption:{stop['id']}")
            placement.update(_shadow_paste(canvas, card, (left + i * (card_w + gap), height * .162), angles[i], scale))
            header_bottom = max(header_bottom, placement["frame_origin_px"][1] + placement["frame_size_px"][1])
            card.close()

        footer = layout.get("footer", [])
        map_top = round(header_bottom + height * .032)
        bottom = round(height * (.925 if footer else .956))
        map_box = (round(width * .052), map_top + round(height * .033), round(width * (.896 if full_map else .506)), bottom - map_top - round(height * .054))
        gallery_box = (round(width * .596), map_top + round(height * .033), round(width * .352), bottom - map_top - round(height * .054))
        route_points, pin_records, segment_records = {}, [], []
        edges = [[start, end] for start, end in zip(order, order[1:])]
        label = "行程示意，非比例地图" if edges else "地点集（顺序未确认）"
        attribution = None
        normalized_segments = []
        map_layer = Image.new("RGBA", (map_box[2], map_box[3]), "#e9ece1")
        if map_mode == "geographic":
            from .maps import validate_geographic, render_basemap, project_point, coordinates
            normalized = validate_geographic(layout, check_files=True)
            map_spec = normalized["basemap"]
            normalized_segments = normalized.get("route_segments", [])
            map_layer.close()
            map_layer, basemap_record = render_basemap(map_spec, (map_box[2], map_box[3]))
            provenance.append({**basemap_record, "kind": "basemap", "poster_box_px": list(map_box)})
            viewport = basemap_record.get("viewport_px", [0, 0, map_box[2], map_box[3]])
            def projected(lon, lat):
                px, py = project_point(lon, lat, map_spec["bounds"], (viewport[2], viewport[3]))
                return viewport[0] + px, viewport[1] + py
            for stop in stops:
                lon, lat = coordinates(stop)
                route_points[stop["id"]] = projected(lon, lat)
            attribution = map_spec["attribution"]
            label = "站点连线，非道路路线" if edges else "地点分布（无已确认顺序）"
            if normalized_segments:
                kinds = {segment["kind"] for segment in normalized_segments}
                label = "记录轨迹（非导航指引）" if kinds == {"recorded_track"} else "规划路线（非实录轨迹）" if kinds == {"planned_route"} else "记录轨迹与规划路线（非导航指引）"
                if len(normalized_segments) < len(edges):
                    label += "；虚线为站点连线"
        else:
            map_draw = ImageDraw.Draw(map_layer)
            # Deliberately abstract paper grid; never invent city blocks/coastlines.
            step = max(18, round(width * .023))
            for x in range(step // 2, map_layer.width, step):
                for y in range(step // 2, map_layer.height, step):
                    map_draw.ellipse((x, y, x + 1, y + 1), fill="#c7d0c2")
            columns = 1 if len(stops) == 2 else 2 if len(stops) <= 8 else 3
            rows = math.ceil(len(stops) / columns)
            for index, stop in enumerate(stops):
                row, col = divmod(index, columns)
                if row % 2:
                    col = columns - col - 1
                route_points[stop["id"]] = ((col + .5) / columns * map_layer.width, (row + .5) / rows * map_layer.height)

        route_draw = ImageDraw.Draw(map_layer)
        segments_by_pair = {(segment["from"], segment["to"]): segment for segment in normalized_segments}
        line_width = max(2, round(4 * scale))
        for start, end in edges:
            segment = segments_by_pair.get((start, end))
            if segment:
                points = [projected(lon, lat) for lon, lat in segment["coordinates"]]
                route_draw.line(points, fill="#fffdf6", width=line_width + max(2, round(3 * scale)), joint="curve")
                route_draw.line(points, fill=RED, width=line_width, joint="curve")
                segment_records.append({"from": start, "to": end, "kind": segment["kind"], "source": segment["source"], "confirmed": True})
                if segment.get("distance"):
                    mid = points[len(points) // 2]
                    distance_text = str(segment["distance"]["value"])
                    _fitted_text(map_layer, distance_text, (max(4, min(map_layer.width - 110 * scale, mid[0] - 55 * scale)), max(4, min(map_layer.height - 25 * scale, mid[1] - 25 * scale)), min(map_layer.width - 8, 110 * scale), 25 * scale), font_path, 18 * scale, min_font, provenance, color=RED, name=f"route_distance:{start}:{end}")
            else:
                _dashed(route_draw, [route_points[start], route_points[end]], RED, line_width, max(5, round(11 * scale)))
                segment_records.append({"from": start, "to": end, "kind": "station_connection", "is_road_route": False})

        # Numbered pins are labels; unknown-order posters explicitly say that
        # these numbers index photos and do not assert travel chronology.
        marker_r = max(10, round(18 * scale))
        pin_centers = []
        for stop in stops:
            anchor = route_points[stop["id"]]
            px, py = anchor
            px = max(marker_r + 3, min(map_layer.width - marker_r - 3, px))
            py = max(marker_r + 3, min(map_layer.height - marker_r - 3, py))
            if map_mode == "geographic":
                for attempt in range(1, 20):
                    if all(math.hypot(px - cx, py - cy) >= marker_r * 2.4 for cx, cy in pin_centers):
                        break
                    angle = attempt * 2.4
                    px = max(marker_r + 3, min(map_layer.width - marker_r - 3, anchor[0] + math.cos(angle) * marker_r * (2 + attempt * .3)))
                    py = max(marker_r + 3, min(map_layer.height - marker_r - 3, anchor[1] + math.sin(angle) * marker_r * (2 + attempt * .3)))
                if (px, py) != anchor:
                    route_draw.line([anchor, (px, py)], fill=MUTED, width=max(1, round(scale)))
            pin_centers.append((px, py))
            route_draw.ellipse((px - marker_r, py - marker_r, px + marker_r, py + marker_r), fill=RED, outline="#fffdf7", width=max(2, round(3 * scale)))
            _fitted_text(map_layer, str(indices[stop["id"]]), (px - marker_r + 2, py - marker_r * .72, marker_r * 2 - 4, marker_r * 1.5), font_path, 24 * scale, max(10, round(13 * scale)), provenance, color="white", align="center", name=f"pin:{stop['id']}")
            if map_mode != "geographic":
                columns = 1 if len(stops) == 2 else 2 if len(stops) <= 8 else 3
                label_width = map_layer.width / columns * .9
                label_height = min(map_layer.height / math.ceil(len(stops) / columns) * .30, height * .038)
                _fitted_text(map_layer, stop["name"], (max(2, px - label_width / 2), py + marker_r + max(4, round(5 * scale)), label_width, label_height), font_path, 20 * scale, min_font, provenance, align="center", name=f"map_stop:{stop['id']}")
            pin_records.append({"stop_id": stop["id"], "index": indices[stop["id"]], "anchor_px": [round(v, 2) for v in anchor], "label_px": [round(px, 2), round(py, 2)]})
        canvas.alpha_composite(map_layer, (map_box[0], map_box[1]))
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((map_box[0], map_box[1], map_box[0] + map_box[2], map_box[1] + map_box[3]), radius=max(3, round(7 * scale)), outline="#ccd0c2", width=max(1, round(scale)))
        map_layer.close()
        _fitted_text(canvas, label, (width * .052, map_top, width * .63, height * .024), font_path, 24 * scale, min_font, provenance, name="route_semantics")
        if not full_map:
            _fitted_text(canvas, "PHOTO NOTES", (gallery_box[0], map_top, gallery_box[2], height * .019), font_path, 14 * scale, min_font, provenance, color=MUTED, name="gallery_label")

        columns = 1 if len(bindings) <= 4 else 2 if len(bindings) <= 10 else 3
        rows = math.ceil(len(bindings) / columns)
        gutter = max(6, round(width * .012))
        cell_w = (gallery_box[2] - gutter * (columns - 1)) // columns
        cell_h = (gallery_box[3] - gutter * (rows - 1)) // rows
        floating_boxes = []
        if full_map:
            cell_w = round(width * .20)
            cell_h = min(round(height * .185), round(map_box[3] * .43))
            floating_boxes = _floating_card_positions((map_box[2], map_box[3]), (cell_w, cell_h),
                                                       [stop["id"] for stop, pid in bindings], route_points, pin_centers, marker_r + round(6 * scale))
            # Draw leaders below the cards so their ends meet the paper edge.
            for (stop, pid), (cx, cy, cw, ch) in zip(bindings, floating_boxes):
                ax, ay = route_points[stop["id"]]
                end = (max(cx, min(cx + cw, ax)), max(cy, min(cy + ch, ay)))
                dx, dy = end[0] - ax, end[1] - ay
                distance = math.hypot(dx, dy)
                center = pin_centers[indices[stop["id"]] - 1]
                if distance and math.hypot(center[0] - ax, center[1] - ay) < .5:
                    ax, ay = ax + dx / distance * (marker_r + 2), ay + dy / distance * (marker_r + 2)
                leader = [(map_box[0] + ax, map_box[1] + ay), (map_box[0] + end[0], map_box[1] + end[1])]
                draw.line(leader, fill="#fffdf7", width=max(3, round(4 * scale)))
                draw.line(leader, fill=RED, width=max(1, round(1.6 * scale)))
        if cell_w < 50 or cell_h < 54:
            raise HappyTripError("LAYOUT_OVERFLOW", "Too many stop-photo bindings for readable callouts. Enlarge layout.size or reduce duplicate bindings; no photo was omitted.")
        for i, (stop, pid) in enumerate(bindings):
            card = Image.new("RGBA", (cell_w, cell_h), "#fffdf7")
            card_draw = ImageDraw.Draw(card)
            card_draw.rectangle((0, 0, cell_w - 1, cell_h - 1), outline="#dedbd1", width=max(1, round(scale)))
            pad = max(4, round(cell_w * .045))
            side_by_side = columns == 1 and not full_map
            caption_h = max(24, round(cell_h * (.45 if map_mode == "geographic" else .29)))
            image_h = cell_h - caption_h - pad * 2
            photo_box = [pad / cell_w, pad / cell_h, .49, (cell_h - pad * 2) / cell_h] if side_by_side else [pad / cell_w, pad / cell_h, (cell_w - pad * 2) / cell_w, image_h / cell_h]
            placement = place_photo(card, stop, pid, photo_box, "callout")
            caption = f"{indices[stop['id']]:02d}  {stop['name']}"
            caption_box = (cell_w * .575, cell_h * .18, cell_w * .385, cell_h * .69) if side_by_side else (pad, image_h + pad * 1.7, cell_w - pad * 2, caption_h - pad)
            if map_mode == "geographic":
                lon, lat = coordinates(stop)
                # Exact coordinates are distinct numeric records. Never wrap a
                # decimal coordinate across lines or mix it into a name/date.
                fields = [(caption, f"callout:{stop['id']}:{pid}")]
                if stop.get("subtitle"):
                    fields.append((stop["subtitle"], f"callout_subtitle:{stop['id']}:{pid}"))
                if stop.get("date"):
                    fields.append((str(stop["date"]["value"]), f"callout_date:{stop['id']}:{pid}"))
                fields.append((f"{abs(lat):.4f}°{'N' if lat >= 0 else 'S'}\n{abs(lon):.4f}°{'E' if lon >= 0 else 'W'}", f"callout_coordinates:{stop['id']}:{pid}"))
                x, y, text_w, text_h = caption_box
                weights = [2 if "coordinates" in name else 1 for value, name in fields]
                total = sum(weights)
                cursor = y
                for (value, name), weight in zip(fields, weights):
                    field_h = text_h * weight / total
                    desired = min(21 * scale, cell_w * .078) if "coordinates" in name else min(23 * scale, cell_w * .085)
                    _fitted_text(card, value, (x, cursor, text_w, field_h - 2), font_path, desired, min_font, provenance, name=name, wrap=False)
                    cursor += field_h
            else:
                if stop.get("subtitle"):
                    caption += "\n" + stop["subtitle"]
                if stop.get("date"):
                    caption += "\n" + str(stop["date"]["value"])
                _fitted_text(card, caption, caption_box, font_path, min(23 * scale, cell_w * .085), min_font, provenance, name=f"callout:{stop['id']}:{pid}")
            if full_map:
                cx, cy, cw, ch = floating_boxes[i]
                x, y = map_box[0] + cx, map_box[1] + cy
                shadow = Image.new("RGBA", (cell_w + 12, cell_h + 12), (0, 0, 0, 0))
                ImageDraw.Draw(shadow).rounded_rectangle((4, 4, cell_w + 4, cell_h + 4), radius=5, fill=(35, 47, 40, 65))
                shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, round(4 * scale))))
                canvas.alpha_composite(shadow, (x - 3, y - 2))
                shadow.close()
            else:
                x, y = gallery_box[0] + (i % columns) * (cell_w + gutter), gallery_box[1] + (i // columns) * (cell_h + gutter)
            canvas.alpha_composite(card, (x, y))
            placement.update({"frame_origin_px": [x, y], "frame_size_px": [cell_w, cell_h], "rotation_degrees": 0})
            if full_map:
                placement["map_anchor_px"] = list(route_points[stop["id"]])
                placement["on_map"] = True
            card.close()
        source_note = attribution or ("编号仅用于照片索引，不代表旅行顺序" if not order else "照片为原始素材排版 · 连线仅表达已确认站点顺序")
        _fitted_text(canvas, source_note, (width * .053, bottom - height * .012, width * .894, height * .027), font_path, 15 * scale, max(10, round(11 * scale)), provenance, color=MUTED, name="map_attribution" if attribution else "map_note")
        if footer:
            footer_text = "   |   ".join(f"{item['label']}  {item['value']}" for item in footer)
            footer_box = (width * .026, height * .952, width * .948, height * .031)
            draw.rectangle((width * .026, height * .947, width * .974, height * .982), fill="#293e39")
            _fitted_text(canvas, footer_text, (footer_box[0] + width * .026, footer_box[1], footer_box[2] - width * .052, footer_box[3]), font_path, 20 * scale, min_font, provenance, color="#fffdf7", name="confirmed_footer")
        from .planner import route_data_fingerprint
        return {"template": "travel_poster", "data_fingerprint": route_data_fingerprint(layout), "ordered_stop_ids": order, "order_confirmed": bool(order), "edges": edges,
                "label": label, "map_mode": map_mode if map_mode == "geographic" or edges else "collection",
                "map_layout": actual_map_layout, "requested_map_layout": requested_map_layout, "fallback_reason": fallback_reason,
                "pins": pin_records, "map_box_px": list(map_box), "route_segments": segment_records,
                "photo_ids": list(by_asset), "source_photo_count": len(by_asset), "photo_binding_count": len(bindings),
                "exact_original_pixels": False, "attribution": attribution}
    finally:
        for image in source_images.values():
            image.close()
