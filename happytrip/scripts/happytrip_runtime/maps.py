"""Local, attributed Web Mercator maps. No network or inferred road routes."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .assets import load_normalized_image, local_path, sha256_file
from .facts import TRUSTED_SOURCES
from .types import HappyTripError

MAX_LAT = 85.0511287798066


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _mercator(lat):
    return math.asinh(math.tan(math.radians(lat)))


def validate_bounds(bounds):
    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4
            or not all(_number(v) for v in bounds)):
        raise HappyTripError("MAP_BOUNDS_INVALID", "Bounds must be [west, south, east, north] in degrees.")
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -MAX_LAT <= south < north <= MAX_LAT):
        raise HappyTripError("MAP_BOUNDS_INVALID", "Use non-wrapping bounds inside the Web Mercator latitude range.")
    return list(bounds)


def _map_aspect(bounds):
    west, south, east, north = validate_bounds(bounds)
    return math.radians(east - west) / (_mercator(north) - _mercator(south))


def project_point(lon, lat, bounds, size):
    """Map WGS84 lon/lat into the full raster viewport; caller adds offsets."""
    west, south, east, north = validate_bounds(bounds)
    if not _number(lon) or not _number(lat) or not (-180 <= lon <= 180 and -MAX_LAT <= lat <= MAX_LAT):
        raise HappyTripError("FACT_COORDINATES_INVALID", "Coordinates must be finite WGS84 longitude/latitude.")
    return ((lon - west) / (east - west) * size[0],
            (_mercator(north) - _mercator(lat)) / (_mercator(north) - _mercator(south)) * size[1])


def coordinates(stop):
    record = stop.get("coordinates")
    if not isinstance(record, dict) or record.get("confirmed") is not True or not isinstance(record.get("source"), str) or record.get("source") not in TRUSTED_SOURCES:
        raise HappyTripError("FACT_COORDINATES_UNKNOWN", "Every geographic stop needs confirmed coordinates and a trusted source.")
    value = record.get("value", record)
    if not isinstance(value, dict):
        raise HappyTripError("FACT_COORDINATES_INVALID", "Use named lat and lon fields.")
    lon, lat = value.get("lon"), value.get("lat")
    project_point(lon, lat, [-180, -MAX_LAT, 180, MAX_LAT], (1, 1))
    return lon, lat


def _inside(point, bounds):
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def validate_basemap(spec, check_files=True):
    if not isinstance(spec, dict):
        raise HappyTripError("MAP_BASEMAP_MISSING", "Geographic mode requires an attributed, georeferenced basemap.")
    data = deepcopy(spec)
    data["bounds"] = validate_bounds(data.get("bounds"))
    if data.get("projection") != "web_mercator":
        raise HappyTripError("MAP_PROJECTION_INVALID", "Only web_mercator rasters are supported; reproject other sources first.")
    for key in ("path", "source", "attribution", "sha256"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise HappyTripError("MAP_PROVENANCE_MISSING", f"Basemap requires {key}.")
    if check_files:
        path = local_path(data["path"])
        if sha256_file(path) != data["sha256"]:
            raise HappyTripError("PROVENANCE_INVALID", "Basemap changed after registration.")
        with load_normalized_image(path) as im:
            if abs((im.width / im.height) / _map_aspect(data["bounds"]) - 1) > .025:
                raise HappyTripError("MAP_PROJECTION_INVALID", "Raster aspect does not match its Mercator bounds; supply the exact exported map extent.")
        data["path"] = str(path)
    return data


def _distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 12742000 * math.asin(min(1, math.sqrt(h)))


def validate_geographic(layout, check_files=True):
    if not isinstance(layout, dict):
        raise HappyTripError("INPUT_INVALID", "Geographic layout must be an object.")
    basemap = validate_basemap(layout.get("basemap"), check_files)
    bounds = basemap["bounds"]
    stops = layout.get("stops", [])
    if not isinstance(stops, list) or not 2 <= len(stops) <= 15 or any(not isinstance(s, dict) for s in stops):
        raise HappyTripError("FACT_STOPS_INVALID", "Geographic maps require 2–15 stops.")
    ids = [s.get("id") for s in stops]
    if any(not isinstance(s, str) or not s for s in ids) or len(set(ids)) != len(ids):
        raise HappyTripError("FACT_STOPS_INVALID", "Stops require unique IDs.")
    points = {s["id"]: coordinates(s) for s in stops}
    if any(not _inside(p, bounds) for p in points.values()):
        raise HappyTripError("MAP_OUT_OF_BOUNDS", "A stop falls outside the basemap; expand the map extent.")
    order = layout.get("ordered_stop_ids", []) if layout.get("order_confirmed") is True else []
    if order and (not isinstance(order, list) or len(order) != len(ids) or any(not isinstance(x, str) for x in order) or set(order) != set(ids)):
        raise HappyTripError("FACT_ORDER_INVALID", "Confirmed order must include every stop exactly once.")
    segments = deepcopy(layout.get("route_segments", []))
    if not isinstance(segments, list):
        raise HappyTripError("MAP_ROUTE_INVALID", "route_segments must be an array.")
    allowed, seen = set(zip(order, order[1:])), set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise HappyTripError("MAP_ROUTE_INVALID", "Each route segment must be an object.")
        pair = (segment.get("from"), segment.get("to"))
        if any(not isinstance(x, str) for x in pair) or pair not in allowed or pair in seen:
            raise HappyTripError("MAP_ROUTE_INVALID", "Segments must bind unique consecutive stops in the confirmed order.")
        seen.add(pair)
        if not isinstance(segment.get("kind"), str) or segment.get("kind") not in {"recorded_track", "planned_route"} or segment.get("confirmed") is not True or not isinstance(segment.get("source"), str) or segment["source"] not in TRUSTED_SOURCES:
            raise HappyTripError("MAP_ROUTE_INVALID", "A segment needs a confirmed trusted source and recorded_track or planned_route kind; use source_reference for URLs.")
        geometry = segment.get("coordinates")
        if not isinstance(geometry, list) or not 2 <= len(geometry) <= 100000:
            raise HappyTripError("MAP_ROUTE_INVALID", "Each segment needs 2–100000 [longitude, latitude] positions.")
        for point in geometry:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise HappyTripError("MAP_ROUTE_INVALID", "Route positions must be [longitude, latitude].")
            project_point(*point, bounds, (1, 1))
            if not _inside(point, bounds):
                raise HappyTripError("MAP_OUT_OF_BOUNDS", "Route geometry falls outside the basemap; expand its extent.")
        if _distance(geometry[0], points[pair[0]]) > 250 or _distance(geometry[-1], points[pair[1]]) > 250:
            raise HappyTripError("MAP_ROUTE_INVALID", "Segment endpoints must be within 250 m of their bound stops; check direction and coordinates.")
    return {"basemap": basemap, "route_segments": segments}


def render_basemap(spec, size):
    data = validate_basemap(spec)
    with load_normalized_image(data["path"]) as image:
        # Contain the map instead of stretching/cropping it; pins use the same viewport.
        scale = min(size[0] / image.width, size[1] / image.height)
        width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
        x, y = (size[0] - width) // 2, (size[1] - height) // 2
        canvas = Image.new("RGBA", size, "#edf0e8")
        canvas.alpha_composite(image.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS), (x, y))
    return canvas, {"kind": "geographic_basemap", **data, "viewport_px": [x, y, width, height]}


def _fit_bounds(bounds, size):
    west, south, east, north = validate_bounds(bounds)
    x0, x1 = math.radians(west), math.radians(east)
    y0, y1 = _mercator(south), _mercator(north)
    ratio = size[0] / size[1]
    if (x1 - x0) / (y1 - y0) < ratio:
        delta = ((y1 - y0) * ratio - (x1 - x0)) / 2
        x0, x1 = x0 - delta, x1 + delta
    else:
        delta = ((x1 - x0) / ratio - (y1 - y0)) / 2
        y0, y1 = y0 - delta, y1 + delta
    return validate_bounds([math.degrees(x0), math.degrees(math.atan(math.sinh(y0))),
                            math.degrees(x1), math.degrees(math.atan(math.sinh(y1)))])


def _draw_geojson(data, bounds, size, font_path=None):
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise HappyTripError("MAP_GEOJSON_INVALID", "Supply a WGS84 GeoJSON FeatureCollection.")
    if len(data["features"]) > 50000 or data.get("crs"):
        raise HappyTripError("MAP_GEOJSON_INVALID", "Use at most 50000 WGS84 features, without a custom CRS.")
    canvas = Image.new("RGB", size, "#eeeae0")
    draw = ImageDraw.Draw(canvas)
    palette = {"water": "#b9d9e4", "park": "#d2dec4", "building": "#dbd5c8", "boundary": "#c4bdab"}
    labels = []
    layers = {"water": 0, "park": 1, "building": 2, "boundary": 3, "minor_road": 4, "road": 5}
    features = data["features"]
    if any(not isinstance(f, dict) or not isinstance(f.get("geometry"), dict) or not isinstance(f.get("properties", {}), dict) for f in features):
        raise HappyTripError("MAP_GEOJSON_INVALID", "Features need geometry and properties objects.")
    if any(not isinstance(f.get("properties", {}).get("kind", "boundary"), str) for f in features):
        raise HappyTripError("MAP_GEOJSON_INVALID", "Feature kind must be a string.")
    point_count = 0

    def line(points):
        nonlocal point_count
        if not isinstance(points, list) or len(points) < 2:
            raise HappyTripError("MAP_GEOJSON_INVALID", "Lines/rings require at least two positions.")
        result = []
        for point in points:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                raise HappyTripError("MAP_GEOJSON_INVALID", "Invalid GeoJSON position.")
            point_count += 1
            if point_count > 1000000:
                raise HappyTripError("MAP_GEOJSON_INVALID", "Map exceeds one million positions.")
            result.append(project_point(point[0], point[1], bounds, size))
        return result

    for feature in sorted(features, key=lambda f: layers.get(f.get("properties", {}).get("kind"), 6)):
        geometry, props = feature["geometry"], feature.get("properties", {})
        kind, typ, coords = props.get("kind", "boundary"), geometry.get("type"), geometry.get("coordinates")
        if not isinstance(typ, str) or not isinstance(coords, list) or not coords:
            raise HappyTripError("MAP_GEOJSON_INVALID", "Geometry needs a type and nonempty coordinates array.")
        if typ in {"Polygon", "MultiPolygon"}:
            polygons = [coords] if typ == "Polygon" else coords
            for rings in polygons:
                if not isinstance(rings, list) or not rings:
                    raise HappyTripError("MAP_GEOJSON_INVALID", "Polygons need closed rings.")
                mask = Image.new("L", size)
                mdraw = ImageDraw.Draw(mask)
                for index, ring in enumerate(rings):
                    if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                        raise HappyTripError("MAP_GEOJSON_INVALID", "GeoJSON polygon rings must close.")
                    mdraw.polygon(line(ring), fill=255 if index == 0 else 0)
                canvas.paste(palette.get(kind, "#e0dbcf"), mask=mask)
                mask.close()
        elif typ in {"LineString", "MultiLineString"}:
            lines = [coords] if typ == "LineString" else coords
            for positions in lines:
                points = line(positions)
                width = max(2, round(size[0] / (280 if kind == "road" else 520)))
                if kind in {"road", "minor_road"}:
                    draw.line(points, fill="#d5cfc0", width=width + 2, joint="curve")
                    draw.line(points, fill="#fffdf4", width=width, joint="curve")
                else:
                    draw.line(points, fill=palette.get(kind, "#cbc5b6"), width=width, joint="curve")
        elif typ == "Point":
            if not isinstance(coords, list) or len(coords) < 2:
                raise HappyTripError("MAP_GEOJSON_INVALID", "Invalid point coordinates.")
            xy = project_point(coords[0], coords[1], bounds, size)
            if props.get("name") and _inside(coords, bounds):
                labels.append((xy, str(props["name"])))
        else:
            raise HappyTripError("MAP_GEOJSON_INVALID", f"Unsupported GeoJSON geometry: {typ}")
    if labels:
        if not font_path:
            raise HappyTripError("TEXT_INVALID", "Named GeoJSON points require --font-path for exact labels.")
        font = ImageFont.truetype(str(local_path(font_path)), max(12, size[0] // 65))
        for xy, name in labels:
            draw.text(xy, name, font=font, fill="#686c62", anchor="mm", stroke_width=2, stroke_fill="#f4f1e6")
    return canvas


def create_basemap(*, output, bounds, source, attribution, image_path=None, geojson_path=None,
                   size=(1400, 1000), font_path=None):
    """Register a supplied raster or render supplied vector data; return direct basemap metadata."""
    if bool(image_path) == bool(geojson_path):
        raise HappyTripError("INPUT_INVALID", "Select exactly one --image or --geojson source.")
    out = Path(output).expanduser().resolve()
    if out.exists() or out.suffix.lower() != ".json":
        raise HappyTripError("OUTPUT_INVALID", "Basemap metadata must be a new .json file.")
    if not isinstance(source, str) or not source.strip() or not isinstance(attribution, str) or not attribution.strip():
        raise HappyTripError("MAP_PROVENANCE_MISSING", "A source reference and visible attribution are required.")
    bounds = validate_bounds(bounds)
    generated = None
    extra = {}
    if geojson_path:
        if len(size) != 2 or any(type(v) is not int or v < 256 or v > 8192 for v in size) or size[0] * size[1] > 16000000:
            raise HappyTripError("OUTPUT_INVALID", "Basemap size must be 256–8192 pixels per axis, up to 16 megapixels.")
        vector = local_path(geojson_path)
        if vector.stat().st_size > 50000000:
            raise HappyTripError("MAP_GEOJSON_INVALID", "GeoJSON exceeds 50 MB.")
        raster = out.with_suffix(".png")
        if raster.exists():
            raise HappyTripError("OUTPUT_INVALID", "Derived basemap PNG must be a new file.")
        bounds = _fit_bounds(bounds, size)
        generated = _draw_geojson(json.loads(vector.read_text(encoding="utf-8")), bounds, tuple(size), font_path)
        extra = {"vector_source_sha256": sha256_file(vector)}
        out.parent.mkdir(parents=True, exist_ok=True)
        with raster.open("xb") as stream:
            generated.save(stream, format="PNG")
        generated.close()
    else:
        raster = local_path(image_path)
    result = {"path": str(raster), "bounds": bounds, "projection": "web_mercator", "source": source,
              "attribution": attribution, "sha256": sha256_file(raster), **extra}
    validate_basemap(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result
