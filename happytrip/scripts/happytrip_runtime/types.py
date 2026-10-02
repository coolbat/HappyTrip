"""JSON-native runtime contracts; all records are dictionaries on disk and in APIs."""
from typing import Any, TypeAlias

Request: TypeAlias = dict[str, Any]
Asset: TypeAlias = dict[str, Any]
Capabilities: TypeAlias = dict[str, Any]
Recommendation: TypeAlias = dict[str, Any]
Plan: TypeAlias = dict[str, Any]
Stage: TypeAlias = dict[str, Any]
ImageRequest: TypeAlias = dict[str, Any]
ImageResult: TypeAlias = dict[str, Any]
ValidationResult: TypeAlias = dict[str, Any]
JobResult: TypeAlias = dict[str, Any]


class HappyTripError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def error_record(exc: HappyTripError) -> dict:
    return {"code": exc.code, "message": str(exc)}
