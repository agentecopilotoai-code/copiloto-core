"""Tests for `app/services/campaign_attribution.attribute_appointment`.

Uses a tiny mocked-conn to exercise the no-match and match branches without
spinning up the DB.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4


class _FakeConn:
    """Returns canned fetchrow results in order."""
    def __init__(self, *rows):
        self._rows = list(rows)

    async def fetchrow(self, sql, *args):
        if not self._rows:
            return None
        return self._rows.pop(0)


def test_attribute_appointment_no_eligible_campaign():
    from app.services.campaign_attribution import attribute_appointment
    conn = _FakeConn(None)  # candidate query returns None

    async def _go():
        return await attribute_appointment(
            conn, tenant_id=uuid4(), appointment_id=uuid4(), contact_id=uuid4(),
        )

    assert asyncio.run(_go()) is None


def test_attribute_appointment_records_new_attribution():
    from app.services.campaign_attribution import attribute_appointment
    campaign_id = uuid4()
    inserted_id = uuid4()
    conn = _FakeConn(
        {'campaign_id': campaign_id, 'touch_at': datetime(2026, 5, 18, tzinfo=UTC)},
        {'id': inserted_id},
    )

    async def _go():
        return await attribute_appointment(
            conn, tenant_id=uuid4(), appointment_id=uuid4(), contact_id=uuid4(),
        )

    assert asyncio.run(_go()) == inserted_id


def test_attribute_appointment_handles_null_touch_at():
    """The candidate row may have `touch_at=None` (defensive — query coalesces
    delivered_at and sent_at). The function still records the attribution."""
    from app.services.campaign_attribution import attribute_appointment
    inserted_id = uuid4()
    conn = _FakeConn(
        {'campaign_id': uuid4(), 'touch_at': None},
        {'id': inserted_id},
    )

    async def _go():
        return await attribute_appointment(
            conn, tenant_id=uuid4(), appointment_id=uuid4(), contact_id=uuid4(),
        )

    assert asyncio.run(_go()) == inserted_id


def test_attribute_appointment_insert_returns_none():
    """If the insert short-circuits (on-conflict no-op) and returns None,
    the function returns None too — defensive against unexpected DB state."""
    from app.services.campaign_attribution import attribute_appointment
    conn = _FakeConn(
        {'campaign_id': uuid4(), 'touch_at': datetime.now(UTC)},
        None,  # insert returns no row
    )

    async def _go():
        return await attribute_appointment(
            conn, tenant_id=uuid4(), appointment_id=uuid4(), contact_id=uuid4(),
        )

    assert asyncio.run(_go()) is None
