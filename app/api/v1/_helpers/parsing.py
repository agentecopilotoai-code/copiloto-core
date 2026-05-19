"""JSON/JSONB parsing helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from typing import Any


def parse_json_object(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return default or {}
    if isinstance(value, dict):
        return value
    return default or {}


def metadata_extracted_text(value: Any) -> str | None:
    metadata = parse_json_object(value, default={})
    extracted_text = metadata.get('extracted_text')
    return extracted_text if isinstance(extracted_text, str) else None


def _coerce_jsonb(value: Any) -> Any:
    """Ensure a value that may arrive as a JSON string is returned as a Python dict/list."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
    return value
