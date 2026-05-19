"""Validators extracted from app/api/v1/routes.py."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


NOTIFICATION_CHANNEL_IDS = ('email', 'wa', 'inapp')


def _validate_digest_recipients(email: str | None, whatsapp: str | None) -> None:
    if not (email or '').strip() and not (whatsapp or '').strip():
        raise HTTPException(
            status_code=400,
            detail='recipient_email or recipient_whatsapp is required',
        )


def _validate_timezone(tz: Any) -> None:
    """Raise 422 if `tz` is not a valid IANA timezone.

    `ZoneInfo(...)` raises `ZoneInfoNotFoundError` for unknown zones; older
    inputs (e.g. trailing slashes) can surface `ValueError` — SEC-010 hardening
    asks us to catch both. None / empty → no-op (handled by the column default).

    codex P2 (UI-016.7-FU review): a non-string JSON value (e.g. `123`) would
    reach `ZoneInfo()` and raise `TypeError` — uncaught, leaking a 500 to the
    caller. Reject non-strings up front with the expected 422.
    """
    if tz is None or tz == '':
        return
    if not isinstance(tz, str):
        raise HTTPException(status_code=422, detail='timezone must be a string')
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f'Invalid timezone: {tz}') from exc


def _validate_notification_matrix(matrix: Any) -> dict:
    """Validate the `notification_matrix` payload.

    Shape: `{event_id (str): {channel_id (str in {email,wa,inapp}): bool}}`.
    Unknown channel ids are rejected; unknown event ids are allowed (the
    catalog of events is frontend-driven and may grow without a backend
    migration).
    """
    if not isinstance(matrix, dict):
        raise HTTPException(status_code=422, detail='notification_matrix must be an object')
    for event_id, channels in matrix.items():
        if not isinstance(event_id, str) or not event_id:
            raise HTTPException(status_code=422, detail='notification_matrix keys must be non-empty strings')
        if not isinstance(channels, dict):
            raise HTTPException(
                status_code=422,
                detail=f'notification_matrix[{event_id}] must be an object',
            )
        for channel_id, enabled in channels.items():
            if channel_id not in NOTIFICATION_CHANNEL_IDS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f'notification_matrix[{event_id}][{channel_id}]: '
                        f'channel must be one of {NOTIFICATION_CHANNEL_IDS}'
                    ),
                )
            if not isinstance(enabled, bool):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f'notification_matrix[{event_id}][{channel_id}]: '
                        'value must be a boolean'
                    ),
                )
    return matrix
