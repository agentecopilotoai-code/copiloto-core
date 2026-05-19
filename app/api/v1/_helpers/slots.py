"""Slot computation helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.api.v1._helpers.parsing import parse_json_object


WEEKDAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def parse_iso_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail='date must use YYYY-MM-DD format') from exc


def working_hours_for_date(capabilities: Any, target_date: datetime) -> list[dict[str, str]]:
    """Read resources.capabilities.working_hours and return franjas of the target weekday."""
    config = parse_json_object(capabilities, default={})
    working_hours = config.get('working_hours')
    if not isinstance(working_hours, dict):
        return []
    weekday_key = WEEKDAY_KEYS[target_date.weekday()]
    franjas = working_hours.get(weekday_key)
    if not isinstance(franjas, list):
        return []
    normalized: list[dict[str, str]] = []
    for franja in franjas:
        if not isinstance(franja, dict):
            continue
        start = franja.get('start')
        end = franja.get('end')
        if isinstance(start, str) and isinstance(end, str) and start and end:
            normalized.append({'start': start, 'end': end})
    return normalized


def slot_start_minutes(value: str) -> int:
    hours, _, minutes = value.partition(':')
    try:
        return int(hours) * 60 + int(minutes or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f'Invalid time format: {value}') from exc


def minutes_to_hhmm(minutes: int) -> str:
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def compute_free_slots(
    franjas: list[dict[str, str]],
    busy_intervals: list[tuple[int, int]],
    duration_minutes: int,
    step_minutes: int | None = None,
) -> list[dict[str, str]]:
    """Yield free slots of `duration_minutes` skipping any overlap with busy_intervals.

    Slots are aligned to the franja start and advance in `step_minutes`
    (defaults to duration_minutes — back-to-back slots).
    """
    if duration_minutes <= 0:
        return []
    step = step_minutes or duration_minutes
    slots: list[dict[str, str]] = []
    for franja in franjas:
        franja_start = slot_start_minutes(franja['start'])
        franja_end = slot_start_minutes(franja['end'])
        if franja_end <= franja_start:
            continue
        cursor = franja_start
        while cursor + duration_minutes <= franja_end:
            slot_start = cursor
            slot_end = cursor + duration_minutes
            overlaps = False
            for busy_start, busy_end in busy_intervals:
                if slot_start < busy_end and busy_start < slot_end:
                    overlaps = True
                    break
            if not overlaps:
                slots.append({
                    'start_time': minutes_to_hhmm(slot_start),
                    'end_time': minutes_to_hhmm(slot_end),
                })
            cursor += step
    return slots
