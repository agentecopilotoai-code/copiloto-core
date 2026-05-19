"""Tenant readiness helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID


def readiness_check(key: str, label: str, ready: bool, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'ready': ready,
        'reason': reason,
        'details': details or {},
    }


def readiness_truthy_object(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict | list | tuple | set):
        return bool(value)
    return bool(str(value).strip()) if isinstance(value, str) else bool(value)


def readiness_positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def readiness_response(tenant_id: UUID, checks: list[dict[str, Any]], smoke_question: str) -> dict[str, Any]:
    reasons = [check['reason'] for check in checks if not check['ready']]
    ready = not reasons
    return {
        'tenant_id': str(tenant_id),
        'checked_at': datetime.now(UTC).isoformat(),
        'status': 'ready' if ready else 'not_ready',
        'ready': ready,
        'reasons': reasons,
        'smoke_question': smoke_question,
        'checks': checks,
    }
