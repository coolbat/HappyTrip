from typing import Protocol

CAPABILITY_NAMES = ("vision", "image_generation", "image_editing", "masked_editing",
                    "multiple_references", "transparent_assets", "local_composition",
                    "exact_text_rendering", "geographic_rendering")


def normalize_capabilities(values=None):
    values = values or {}
    result = {name: values.get(name, "unknown") for name in CAPABILITY_NAMES}
    for name, value in result.items():
        if value is not True and value is not False and value != "unknown":
            raise ValueError(f"Invalid capability {name}: use true, false or unknown")
    limit = values.get("max_reference_images")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("max_reference_images must be null or positive integer")
    result["max_reference_images"] = limit
    return result


class ImageAdapter(Protocol):
    def capabilities(self) -> dict: ...
    def execute(self, image_request: dict) -> dict: ...
