"""Offline synthetic control-flow fixture. Never counts as real image validation."""
from pathlib import Path
from PIL import Image, ImageDraw
from .base import CAPABILITY_NAMES


class MockAdapter:
    simulated = True

    def capabilities(self):
        return {**{k: True for k in CAPABILITY_NAMES}, "geographic_rendering": False,
                "max_reference_images": 5}

    def execute(self, image_request):
        root = Path(image_request["output_dir"])
        root.mkdir(parents=True, exist_ok=True)
        path = root / (image_request["stage_id"] + ".png")
        picture = Image.new("RGB", (320, 240), "#f3eddc")
        ImageDraw.Draw(picture).text((20, 100), "SIMULATED - NOT A PHOTO RESULT", fill="#73472a")
        picture.save(path)
        return {"status": "candidate", "path": str(path.resolve()), "simulated": True,
                "provider_request_id": None, "actual_cost": None}
