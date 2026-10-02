"""Structural checks are separate from unperformed human/vision acceptance."""
from pathlib import Path

from .assets import load_normalized_image, local_path, sha256_file
from .compositor import verify_protected_pixels
from .types import HappyTripError


def validate_image_file(path):
    try:
        resolved = local_path(path)
        image = load_normalized_image(resolved)
        result = {"status": "pass", "reason": "Readable image file exists.", "path": str(resolved),
                  "width": image.width, "height": image.height, "sha256": sha256_file(resolved)}
        image.close()
        return result
    except (HappyTripError, OSError) as exc:
        return {"status": "fail", "reason": str(exc), "path": str(path) if path else None}


def validate_result(job_result, plan=None):
    checks = []
    for asset in job_result.get("image_assets", []):
        path = asset.get("path", asset.get("working_path")) if isinstance(asset, dict) else asset
        checks.append({"name": "file", **validate_image_file(path)})
    if not checks:
        return {"status": "not_run", "reason": "No actual image files are available.", "checks": []}
    if any(check["status"] == "fail" for check in checks):
        return {"status": "fail", "reason": "One or more output images cannot be read.", "checks": checks}
    simulated = job_result.get("simulated") or any(isinstance(asset, dict) and asset.get("simulated") for asset in job_result.get("image_assets", []))
    if simulated:
        return {"status": "not_run", "reason": "Simulated images are control-flow evidence only.", "checks": checks}
    # Existence, hashes and pixel comparisons cannot establish identity or aesthetic acceptance.
    return {"status": "not_run", "reason": "File checks passed; mode-specific visual acceptance is still required.", "checks": checks}
