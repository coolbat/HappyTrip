"""Read-only raster ingestion and orientation-normalized, metadata-free copies."""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
import tempfile
import uuid

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .types import HappyTripError

ROLES = frozenset({"base", "person", "scene", "object", "food", "drink", "pet", "container", "suitcase", "reference", "style", "identity", "background"})
MAX_PIXELS = 50_000_000


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def local_path(ref, resolver=None):
    if not isinstance(ref, (str, Path)) or not str(ref).strip():
        raise HappyTripError("ASSET_MISSING", "A real image reference is required; example IDs are not files.")
    resolved = resolver(str(ref)) if resolver else ref
    if isinstance(resolved, dict):
        resolved = resolved.get("path") or resolved.get("ref")
    if not isinstance(resolved, (str, Path)):
        raise HappyTripError("ASSET_MISSING", f"Reference could not be resolved: {ref}")
    path = Path(resolved).expanduser().resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise HappyTripError("ASSET_MISSING", f"Missing or empty image: {ref}")
    return path


def load_normalized_image(path):
    """Return an independent RGB(A) sRGB raster; source bytes remain untouched."""
    try:
        with Image.open(path) as source:
            if source.width * source.height > MAX_PIXELS or getattr(source, "n_frames", 1) != 1:
                raise HappyTripError("ASSET_INVALID", "Only single-frame images up to 50 megapixels are accepted.")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            mode = "RGBA" if "A" in oriented.getbands() or "transparency" in source.info else "RGB"
            profile = source.info.get("icc_profile")
            if profile:
                try:
                    rgb = ImageCms.profileToProfile(oriented, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                                    ImageCms.createProfile("sRGB"), outputMode="RGB")
                    if mode == "RGBA":
                        rgb.putalpha(oriented.convert("RGBA").getchannel("A"))
                    image = rgb
                except (OSError, ValueError, ImageCms.PyCMSError) as exc:
                    raise HappyTripError("ASSET_INVALID", "The image color profile cannot be normalized.") from exc
            else:
                image = oriented.convert(mode)
            # A new image removes EXIF, GPS, text chunks, ICC and other source metadata.
            clean = Image.new(mode, image.size)
            clean.paste(image)
            return clean
    except HappyTripError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HappyTripError("ASSET_INVALID", f"Not a readable single image: {path}") from exc


def validate_box(box):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise HappyTripError("REGION_INVALID", "Regions must be normalized [x, y, width, height].")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
        raise HappyTripError("REGION_INVALID", "Region coordinates must be finite numbers.")
    x, y, width, height = box
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 + 1e-10 or y + height > 1 + 1e-10:
        raise HappyTripError("REGION_INVALID", "Regions must lie entirely within the normalized canvas.")
    return [float(v) for v in box]


def validate_mask(path, size):
    path = local_path(path)
    try:
        with Image.open(path) as mask:
            mask.load()
            if mask.size != tuple(size):
                raise HappyTripError("MASK_INVALID", f"Mask dimensions {mask.size} do not match normalized image {tuple(size)}.")
            if mask.getexif().get(274, 1) != 1 or getattr(mask, "n_frames", 1) != 1:
                raise HappyTripError("MASK_INVALID", "Mask must already use the normalized image orientation.")
            if mask.mode not in {"1", "L"}:
                raise HappyTripError("MASK_INVALID", "Use a grayscale mask: 0 protects; values above 0 authorize editing.")
            return mask.convert("L")
    except HappyTripError:
        raise
    except (OSError, ValueError) as exc:
        raise HappyTripError("MASK_INVALID", f"Unreadable mask: {path}") from exc


def resolve_assets(request, resolver=None, workdir=None):
    photos = request.get("photos", request.get("assets", []))
    if not isinstance(photos, list) or not photos:
        raise HappyTripError("ASSET_MISSING", "Supply selected photo assets; a document alone is not a photo.")
    directory = Path(workdir).expanduser().resolve() if workdir else Path(tempfile.mkdtemp(prefix="happytrip-assets-"))
    directory.mkdir(parents=True, exist_ok=True)
    assets, ids = [], set()
    for index, record in enumerate(photos):
        if not isinstance(record, dict):
            raise HappyTripError("ASSET_INVALID", "Each photo must include photo_id, ref and roles.")
        photo_id = record.get("photo_id", f"p{index + 1:02}")
        if not isinstance(photo_id, str) or not photo_id.strip() or photo_id in ids:
            raise HappyTripError("ASSET_INVALID", "Photo IDs must be nonempty and unique.")
        ids.add(photo_id)
        roles = record.get("roles", ["reference"])
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in ROLES for role in roles):
            raise HappyTripError("ROLE_INVALID", f"Unsupported image roles for {photo_id}.")
        source = local_path(record.get("ref"), resolver)
        original_hash = sha256_file(source)
        image = load_normalized_image(source)
        copy_path = directory / f"asset-{index + 1:03}-{uuid.uuid4().hex[:12]}.png"
        with copy_path.open("xb") as out:
            image.save(out, format="PNG")
        asset = {"photo_id": photo_id, "ref": str(source), "working_path": str(copy_path), "roles": list(roles),
                 "width": image.width, "height": image.height, "orientation_normalized": True,
                 "input_sha256": original_hash, "working_sha256": sha256_file(copy_path)}
        image.close()
        if sha256_file(source) != original_hash:
            raise HappyTripError("ASSET_CHANGED", f"Source changed during ingestion: {photo_id}")
        if record.get("mask_ref"):
            mask_path = local_path(record["mask_ref"], resolver)
            mask = validate_mask(mask_path, (asset["width"], asset["height"]))
            normalized_mask = directory / f"mask-{index + 1:03}-{uuid.uuid4().hex[:12]}.png"
            with normalized_mask.open("xb") as out:
                mask.save(out, format="PNG")
            mask.close()
            asset["mask_path"] = str(normalized_mask)
        assets.append(asset)
    by_id = {asset["photo_id"]: asset for asset in assets}
    region_groups = [(field, request.get(field, [])) for field in ("targets", "protected", "allowed_regions")]
    contract = request.get("edit_contract", {})
    if isinstance(contract, dict):
        region_groups.extend((f"edit_contract.{field}", contract.get(field, [])) for field in ("allowed_regions", "protected_regions"))
    for field, regions in region_groups:
        if not isinstance(regions, list):
            raise HappyTripError("REGION_INVALID", f"{field} must be a list.")
        for region in regions:
            if isinstance(region, (list, tuple)) and field not in {"targets", "protected"}:
                if len(assets) != 1:
                    raise HappyTripError("REGION_INVALID", "Multi-photo region boxes require an explicit photo_id.")
                validate_box(region)
                continue
            if isinstance(region, dict) and not region.get("photo_id") and len(assets) == 1 and field not in {"targets", "protected"}:
                region = {**region, "photo_id": assets[0]["photo_id"]}
            if not isinstance(region, dict) or region.get("photo_id") not in by_id:
                raise HappyTripError("ASSET_MISSING", f"{field} contains an unregistered photo_id.")
            for box_field in ("box", "bbox"):
                if box_field in region:
                    validate_box(region[box_field])
            if region.get("coordinate_space", "normalized") != "normalized":
                raise HappyTripError("REGION_INVALID", "Coordinates must reference the normalized image.")
            if region.get("mask_ref"):
                asset = by_id[region["photo_id"]]
                validate_mask(local_path(region["mask_ref"], resolver), (asset["width"], asset["height"])).close()
    masks = request.get("masks", [])
    if not isinstance(masks, list):
        raise HappyTripError("MASK_INVALID", "masks must be a list of image bindings.")
    for index, record in enumerate(masks):
        if not isinstance(record, dict) or record.get("photo_id") not in by_id:
            raise HappyTripError("ASSET_MISSING", "Every mask requires a registered photo_id.")
        asset = by_id[record["photo_id"]]
        mask = validate_mask(local_path(record.get("ref", record.get("mask_ref")), resolver), (asset["width"], asset["height"]))
        output = directory / f"bound-mask-{index + 1:03}-{uuid.uuid4().hex[:12]}.png"
        with output.open("xb") as stream:
            mask.save(stream, format="PNG")
        mask.close()
        asset.setdefault("masks", []).append({"path": str(output), "sha256": sha256_file(output)})
    return assets
