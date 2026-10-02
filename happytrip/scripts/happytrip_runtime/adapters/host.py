"""Native host handoff, not a network client or an invented tool API."""
from .base import normalize_capabilities


class HostAdapter:
    simulated = False
    deferred = True

    def __init__(self, capabilities=None):
        self._capabilities = normalize_capabilities(capabilities)

    def capabilities(self):
        return dict(self._capabilities)

    def execute(self, image_request):
        return {"status": "prompt_only", "simulated": False, "actual_cost": None,
                "error": "Native host must reserve the stage, call its real tool, then import the actual file."}
