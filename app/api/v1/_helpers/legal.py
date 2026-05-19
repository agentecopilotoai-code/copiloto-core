"""Legal/HTML helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations


def html_escape_attr(value: str) -> str:
    return value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')
