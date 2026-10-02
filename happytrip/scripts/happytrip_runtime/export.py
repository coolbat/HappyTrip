"""Export real metadata-free images and a truthful, redacted delivery manifest."""
import json
from pathlib import Path

from .assets import load_normalized_image, local_path, sha256_file
from .types import HappyTripError

_PRIVATE_KEYS = {"api_key", "apikey", "token", "access_token", "secret", "password", "authorization", "credentials", "gps", "latitude", "longitude", "coordinates", "lat", "lon", "lng", "ref", "working_path", "input_path", "references"}


def _public(value):
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key.lower() not in _PRIVATE_KEYS and not any(part in key.lower() for part in ("secret", "password", "api_key", "token"))}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def export_result(job_result, destination):
    """Return exported Asset-like records; candidates remain candidates in manifest.json."""
    records = job_result.get("image_assets", [])
    if not records:
        raise HappyTripError("ASSET_MISSING", "There are no actual result images to export.")
    sources = []
    for record in records:
        path = record.get("path", record.get("working_path")) if isinstance(record, dict) else record
        source = local_path(path)
        image = load_normalized_image(source)
        image.close()
        sources.append(source)
    target = Path(destination).expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise HappyTripError("OUTPUT_INVALID", "Export destination must be a directory.")
    outputs = [target / f"image-{index + 1:03}.png" for index in range(len(sources))]
    manifest = target / "manifest.json"
    if any(path.exists() or path.resolve() in sources for path in outputs + [manifest]):
        raise HappyTripError("OUTPUT_INVALID", "Export refuses to overwrite existing files or image sources.")
    target.mkdir(parents=True, exist_ok=True)
    exported = []
    for index, (source, output) in enumerate(zip(sources, outputs)):
        image = load_normalized_image(source)
        with output.open("xb") as stream:
            image.save(stream, format="PNG")
        exported.append({"photo_id": f"export-{index + 1:03}", "path": str(output), "width": image.width, "height": image.height,
                         "sha256": sha256_file(output), "source_sha256": sha256_file(source), "simulated": bool(job_result.get("simulated") or (isinstance(records[index], dict) and records[index].get("simulated")))})
        image.close()
    delivery = {"job_id": job_result.get("job_id"), "mode": job_result.get("mode"), "status": job_result.get("status", "candidate"),
                "validation_status": job_result.get("validation_status", "not_run"), "simulated": bool(job_result.get("simulated")),
                "image_assets": [{**record, "path": Path(record["path"]).name} for record in exported],
                "warnings": _public(job_result.get("warnings", [])), "edit_summary": _public(job_result.get("edit_summary", [])),
                "provenance": _public(job_result.get("provenance", [])), "actual_cost": job_result.get("actual_cost")}
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(delivery, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return exported
