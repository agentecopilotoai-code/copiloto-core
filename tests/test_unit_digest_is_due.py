"""Tests for app/services/digest.is_due edge cases."""
from __future__ import annotations

from datetime import UTC, datetime



def test_is_due_invalid_cadence_returns_false():
    from app.services.digest import is_due
    assert is_due(cadence='hourly', tz_name='America/Bogota',
                  now_utc=datetime.now(UTC), last_sent_at=None) is False


def test_is_due_before_delivery_hour_returns_false():
    """Before 8am local → not due."""
    from app.services.digest import is_due
    # 5am Bogota = 10am UTC
    now = datetime(2026, 5, 19, 10, 0, tzinfo=UTC)
    # 5am Bogota
    assert is_due(cadence='daily', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=None) is False


def test_is_due_after_delivery_hour_returns_false():
    """After 9am local → not due."""
    from app.services.digest import is_due
    # 10am Bogota = 3pm UTC
    now = datetime(2026, 5, 19, 15, 0, tzinfo=UTC)
    assert is_due(cadence='daily', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=None) is False


def test_is_due_weekly_only_monday():
    """Weekly cadence: not Monday → not due."""
    from app.services.digest import is_due
    # 8am Bogota = 1pm UTC on Tuesday 2026-05-19
    now = datetime(2026, 5, 19, 13, 0, tzinfo=UTC)
    assert is_due(cadence='weekly', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=None) is False


def test_is_due_weekly_monday_at_8am_due():
    from app.services.digest import is_due
    # Monday 2026-05-18 at 8am Bogota = 1pm UTC
    now = datetime(2026, 5, 18, 13, 0, tzinfo=UTC)
    assert is_due(cadence='weekly', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=None) is True


def test_is_due_daily_at_8am_first_time():
    from app.services.digest import is_due
    now = datetime(2026, 5, 19, 13, 0, tzinfo=UTC)  # Tue 8am Bogota
    assert is_due(cadence='daily', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=None) is True


def test_is_due_daily_already_sent_today_blocks():
    from app.services.digest import is_due
    now = datetime(2026, 5, 19, 13, 0, tzinfo=UTC)
    last_sent = datetime(2026, 5, 19, 13, 30, tzinfo=UTC)  # already sent today
    assert is_due(cadence='daily', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=last_sent) is False


def test_is_due_daily_yesterday_due_again():
    from app.services.digest import is_due
    now = datetime(2026, 5, 19, 13, 0, tzinfo=UTC)
    last_sent = datetime(2026, 5, 18, 13, 30, tzinfo=UTC)  # yesterday
    assert is_due(cadence='daily', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=last_sent) is True


def test_is_due_weekly_already_sent_this_week():
    from app.services.digest import is_due
    # Monday 2026-05-18 8am Bogota
    now = datetime(2026, 5, 18, 13, 0, tzinfo=UTC)
    # Sent on Tuesday 2026-05-19 — that's same ISO week (Tue is after Mon)
    last_sent = datetime(2026, 5, 19, 13, 30, tzinfo=UTC)
    assert is_due(cadence='weekly', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=last_sent) is False


def test_is_due_weekly_sent_last_week_due_again():
    from app.services.digest import is_due
    # Monday 2026-05-18 8am Bogota
    now = datetime(2026, 5, 18, 13, 0, tzinfo=UTC)
    # Sent last Monday 2026-05-11
    last_sent = datetime(2026, 5, 11, 13, 30, tzinfo=UTC)
    assert is_due(cadence='weekly', tz_name='America/Bogota',
                  now_utc=now, last_sent_at=last_sent) is True


# ═══ safe_zone fallback ═════════════════════════════════════════════════


def test_safe_zone_invalid_falls_back():
    from app.services.digest import safe_zone
    z = safe_zone('Not/A/Real/TZ')
    # Defaults to UTC or some default; just verify it doesn't raise
    assert z is not None


def test_safe_zone_valid():
    from app.services.digest import safe_zone
    z = safe_zone('America/Bogota')
    assert z is not None
