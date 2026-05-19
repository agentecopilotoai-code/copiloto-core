"""Analytics range + funnel helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException


def _resolve_analytics_range(from_date: str | None, to_date: str | None) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    end = date.fromisoformat(to_date) if to_date else today
    start = date.fromisoformat(from_date) if from_date else (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=400, detail='from_date must be on or before to_date')
    return start, end


def _range_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    range_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    range_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return range_start, range_end


def _funnel_step(label: str, count: int, prev_count: int, top_count: int) -> dict:
    return {
        'step': label,
        'count': count,
        'conversion_from_previous_pct': (
            round(count / prev_count * 100, 1) if prev_count else 0.0
        ),
        'conversion_from_top_pct': (
            round(count / top_count * 100, 1) if top_count else 0.0
        ),
    }
