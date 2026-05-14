"""Static tests for TASK-0067 — Resumen periódico al manager.

Covers:
- Schema: tabla ``digest_subscriptions`` con cadence check, RLS y trigger.
- ``is_due``: enforce ventana 08:00 + idempotencia con ``last_sent_at`` +
  lunes-only para weekly.
- Builders ``build_daily_digest`` / ``build_weekly_digest`` arman subject,
  text, html y components con los KPIs documentados en el backlog
  (snapshot del payload).
- Worker está wireado en ``docker-compose.yml``.
- Endpoints CRUD ``/v1/tenants/{id}/digest/subscriptions`` existen y se
  apoyan en ``tenant_admin_router``.
- ``coreApi.js`` expone los helpers del admin panel.
- Wizard renderiza el panel ``DigestSubscriptionsPanel`` en la pestaña
  Notificaciones.
- WhatsApp template names son ``digest_daily_v1`` / ``digest_weekly_v1``.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.config import get_settings
from app.services.digest import (
    CADENCE_DAILY,
    CADENCE_WEEKLY,
    DELIVERY_HOUR_LOCAL,
    WHATSAPP_DIGEST_DAILY_TEMPLATE,
    WHATSAPP_DIGEST_TEMPLATE_LOCALE,
    WHATSAPP_DIGEST_WEEKLY_TEMPLATE,
    build_daily_digest,
    build_weekly_digest,
    is_due,
    safe_zone,
    whatsapp_template_for_cadence,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
COMPOSE = Path('docker-compose.yml')
WORKER = Path('app/workers/digest_worker.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')


def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))
SCHEMAS = Path('app/api/v1/schemas.py')


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_digest_subscriptions_table():
    source = SCHEMA.read_text()
    assert 'create table app.digest_subscriptions (' in source
    assert "cadence text not null check (cadence in ('daily','weekly'))" in source
    assert 'enabled boolean not null default true' in source
    assert 'last_sent_at timestamptz' in source
    assert 'tenant_id uuid not null references app.tenants(id) on delete cascade' in source
    assert 'chk_digest_subscriptions_recipient' in source
    assert 'ix_digest_subscriptions_tenant' in source
    assert 'ix_digest_subscriptions_due' in source


def test_schema_enables_rls_and_policy_loop_for_digest_subscriptions():
    source = SCHEMA.read_text()
    assert 'alter table app.digest_subscriptions enable row level security' in source
    # La política se crea por el loop genérico sobre el array de nombres.
    assert "'digest_subscriptions'" in source
    assert 'trg_digest_subscriptions_touch' in source


# ───── is_due ──────────────────────────────────────────────────────────────


def _utc_for(tz_name: str, local_dt: datetime) -> datetime:
    return local_dt.replace(tzinfo=ZoneInfo(tz_name)).astimezone(UTC)


def test_is_due_blocks_outside_delivery_window():
    tz = 'America/Bogota'
    early_local = datetime(2026, 5, 12, 7, 30)
    late_local = datetime(2026, 5, 12, 10, 0)
    in_window = datetime(2026, 5, 12, 8, 15)
    assert is_due(
        cadence=CADENCE_DAILY,
        now_utc=_utc_for(tz, early_local),
        tz_name=tz,
        last_sent_at=None,
    ) is False
    assert is_due(
        cadence=CADENCE_DAILY,
        now_utc=_utc_for(tz, late_local),
        tz_name=tz,
        last_sent_at=None,
    ) is False
    assert is_due(
        cadence=CADENCE_DAILY,
        now_utc=_utc_for(tz, in_window),
        tz_name=tz,
        last_sent_at=None,
    ) is True


def test_is_due_weekly_only_on_monday_and_respects_iso_week_idempotency():
    tz = 'America/Bogota'
    # Martes 12-may-2026 08:15 → no es lunes, weekly no debe disparar.
    tuesday_local = datetime(2026, 5, 12, 8, 15)
    assert is_due(
        cadence=CADENCE_WEEKLY,
        now_utc=_utc_for(tz, tuesday_local),
        tz_name=tz,
        last_sent_at=None,
    ) is False
    # Lunes 11-may-2026 08:15 → sí.
    monday_local = datetime(2026, 5, 11, 8, 15)
    monday_utc = _utc_for(tz, monday_local)
    assert is_due(
        cadence=CADENCE_WEEKLY,
        now_utc=monday_utc,
        tz_name=tz,
        last_sent_at=None,
    ) is True
    # last_sent_at del mismo lunes (semana ISO igual) → bloquea.
    last_sent_same_week = _utc_for(tz, monday_local.replace(minute=5))
    assert is_due(
        cadence=CADENCE_WEEKLY,
        now_utc=monday_utc,
        tz_name=tz,
        last_sent_at=last_sent_same_week,
    ) is False
    # last_sent_at del lunes pasado (otra semana ISO) → permite.
    prev_monday = _utc_for(tz, monday_local - timedelta(days=7))
    assert is_due(
        cadence=CADENCE_WEEKLY,
        now_utc=monday_utc,
        tz_name=tz,
        last_sent_at=prev_monday,
    ) is True


def test_is_due_daily_blocks_when_last_sent_today_local():
    tz = 'America/Bogota'
    today_local = datetime(2026, 5, 12, 8, 30)
    now_utc = _utc_for(tz, today_local)
    sent_today = _utc_for(tz, today_local.replace(hour=8, minute=5))
    sent_yesterday = _utc_for(tz, today_local - timedelta(days=1))
    assert is_due(
        cadence=CADENCE_DAILY,
        now_utc=now_utc,
        tz_name=tz,
        last_sent_at=sent_today,
    ) is False
    assert is_due(
        cadence=CADENCE_DAILY,
        now_utc=now_utc,
        tz_name=tz,
        last_sent_at=sent_yesterday,
    ) is True


def test_safe_zone_falls_back_to_utc_for_invalid_timezone():
    zone = safe_zone('Mars/Curiosity')
    assert zone.key == 'UTC'
    assert safe_zone('America/Bogota').key == 'America/Bogota'


# ───── Builders (snapshot) ─────────────────────────────────────────────────


class _DigestConn:
    """Stub mínimo que devuelve filas/conteos predefinidos por consulta.

    El builder hace 6 queries en daily y N en weekly; mapeamos cada query a
    un valor según una heurística por substring para no acoplarnos al SQL
    exacto (lo testea Postgres en runtime). El snapshot mira la salida.
    """

    def __init__(self, *, weekly: bool = False):
        self.calls: list[tuple[str, tuple]] = []
        self.weekly = weekly

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        q = query.lower()
        # _appointments_for_day variants devuelven {'count': N}.
        # Discriminamos por el set de estados:
        #   - ('no_show',) → no-shows de ayer
        #   - ('scheduled','confirmed') → citas para mañana
        #   - ('confirmed','completed') → citas confirmadas hoy
        if 'count(*)::int as count' in q and 'app.appointments' in q and 'status = any' in q:
            statuses = args[3]
            if 'no_show' in statuses:
                return {'count': 1}
            if 'scheduled' in statuses:
                return {'count': 4}
            if 'completed' in statuses:
                return {'count': 6}
            return {'count': 0}
        if 'app.messages' in q and 'direction = \'inbound\'' in q:
            return {'count': 42}
        if 'with leads as' in q and 'engaged as' in q:
            return {'leads': 10, 'engaged': 7, 'scheduled': 3, 'completed': 2}
        if 'sum(s.price_amount)' in q:
            # ingreso semana actual vs semana pasada — alternamos por orden.
            if not hasattr(self, '_revenue_idx'):
                self._revenue_idx = 0
            values = [1_500_000.0, 1_000_000.0]
            v = values[self._revenue_idx]
            self._revenue_idx = min(self._revenue_idx + 1, 1)
            return {'revenue': v}
        if 'completed as' in q and 'count(*) filter (where ct >= 2)' in q:
            return {'recurring': 4, 'total': 10}
        return None

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        q = query.lower()
        if 'appointment_feedback' in q:
            return [
                {
                    'contact_name': 'Ana',
                    'rating': 1,
                    'comment': 'Mal servicio',
                    'created_at': datetime.now(UTC),
                },
            ]
        if 'campaign_attributions' in q:
            return [
                {'name': 'Día de la Madre', 'conversions': 7},
            ]
        if 'app.appointments a' in q and 'group by 1' in q and 'limit' in q:
            return [
                {'name': 'Corte de cabello', 'count': 12},
                {'name': 'Manicuria', 'count': 9},
            ]
        return []


def test_build_daily_digest_returns_six_kpis_and_components():
    conn = _DigestConn()
    today = datetime(2026, 5, 12).date()
    result = asyncio.run(
        build_daily_digest(
            conn,
            tenant_id=uuid4(),
            tz_name='America/Bogota',
            today_local=today,
        )
    )
    kpis = result['kpis']
    # Los 6 KPIs del backlog: confirmadas hoy, mañana, no-shows ayer,
    # mensajes 24h, funnel, top quejas.
    assert kpis['confirmed_today'] == 6
    assert kpis['appointments_tomorrow'] == 4
    assert kpis['no_shows_yesterday'] == 1
    assert kpis['messages_received_24h'] == 42
    assert kpis['funnel'] == {'leads': 10, 'engaged': 7, 'scheduled': 3, 'completed': 2}
    assert kpis['complaints'] and kpis['complaints'][0]['contact_name'] == 'Ana'
    # Subject y components estables.
    assert result['subject'] == '[CopilotoIA] Resumen diario — 2026-05-12'
    assert 'Resumen diario del 2026-05-12' in result['text']
    components = result['whatsapp_components']
    assert components[0]['type'] == 'body'
    params = [p['text'] for p in components[0]['parameters']]
    assert params == ['2026-05-12', '6', '4', '1', '42']


def test_build_weekly_digest_includes_revenue_delta_and_top_services():
    conn = _DigestConn(weekly=True)
    monday = datetime(2026, 5, 11).date()
    result = asyncio.run(
        build_weekly_digest(
            conn,
            tenant_id=uuid4(),
            tz_name='America/Bogota',
            monday_local=monday,
            currency='COP',
        )
    )
    kpis = result['kpis']
    assert kpis['week_start_local'] == '2026-05-11'
    assert kpis['revenue_week'] == 1_500_000.0
    assert kpis['revenue_last_week'] == 1_000_000.0
    assert kpis['revenue_delta_pct'] == 50.0
    assert kpis['retention_pct_90d'] == 40.0
    assert kpis['top_services'][0]['name'] == 'Corte de cabello'
    assert kpis['top_campaigns'][0]['name'] == 'Día de la Madre'
    # Sub-block daily presente para reusar.
    assert kpis['daily']['confirmed_today'] == 6
    # Subject + components estables.
    assert result['subject'] == '[CopilotoIA] Resumen semanal — semana del 2026-05-11'
    params = [p['text'] for p in result['whatsapp_components'][0]['parameters']]
    assert params[0] == '2026-05-11'
    assert params[2] == '+50.0%'
    assert params[3] == '40.0%'


def test_whatsapp_template_for_cadence_picks_right_template():
    assert whatsapp_template_for_cadence(CADENCE_DAILY) == WHATSAPP_DIGEST_DAILY_TEMPLATE
    assert whatsapp_template_for_cadence(CADENCE_WEEKLY) == WHATSAPP_DIGEST_WEEKLY_TEMPLATE
    assert WHATSAPP_DIGEST_TEMPLATE_LOCALE == 'es'
    assert DELIVERY_HOUR_LOCAL == 8


# ───── Worker / compose ────────────────────────────────────────────────────


def test_worker_is_wired_in_docker_compose():
    source = COMPOSE.read_text()
    assert 'digest-worker:' in source
    assert 'python3 -m app.workers.digest_worker' in source


def test_worker_module_exists_and_dispatches_idempotently():
    source = WORKER.read_text()
    assert 'def run_digest_cycle' in source
    # Idempotencia: solo actualiza last_sent_at tras delivered.
    assert 'update app.digest_subscriptions set last_sent_at' in source
    # Reusa el SMTP de operator_alerts (no duplica config SMTP).
    assert 'from app.services.operator_alerts import' in source
    assert '_send_email_smtp' in source


# ───── API + schemas ───────────────────────────────────────────────────────


def test_api_routes_expose_digest_subscriptions_crud():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/digest/subscriptions')" in source
    assert "@tenant_admin_router.post(" in source and '/digest/subscriptions' in source
    assert "@tenant_admin_router.patch(" in source and '/digest/subscriptions/{subscription_id}' in source
    assert "@tenant_admin_router.delete(" in source and '/digest/subscriptions/{subscription_id}' in source
    # Validación de al menos un destinatario.
    assert '_validate_digest_recipients' in source


def test_pydantic_schemas_expose_digest_models():
    source = SCHEMAS.read_text()
    assert 'class DigestSubscriptionCreate' in source
    assert 'class DigestSubscriptionUpdate' in source
    assert "pattern='^(daily|weekly)$'" in source


# ───── Admin Panel ─────────────────────────────────────────────────────────


def test_core_api_helpers_for_digest_subscriptions_exist():
    source = CORE_API.read_text()
    for name in (
        'listDigestSubscriptions',
        'createDigestSubscription',
        'updateDigestSubscription',
        'deleteDigestSubscription',
    ):
        assert f'export function {name}' in source


def test_tomorrow_appointments_uses_schema_compliant_statuses():
    """El check de ``appointments.status`` solo admite scheduled|confirmed|
    completed|cancelled|no_show; el digest no debe pedir estados inexistentes
    (``pending`` / ``rescheduled``) o se pierde la cobertura de mañana."""
    src = Path('app/services/digest.py').read_text()
    # La call a tomorrow_range usa el statuses tupla bien tipado.
    assert "starts_in_utc=tomorrow_range" in src
    snippet = src.split('starts_in_utc=tomorrow_range', 1)[1].split(')', 1)[0]
    assert "'scheduled'" in snippet
    assert "'confirmed'" in snippet
    # Sin estados inválidos.
    assert "'pending'" not in snippet
    assert "'rescheduled'" not in snippet


def test_weekly_digest_default_window_summarizes_completed_week():
    """Cuando el worker dispara el lunes y monday_local viene en None, el
    digest debe resumir la semana **completada** (Lun..Dom anterior), no la
    que recién empieza. Verificamos con un stub de fecha controlada."""
    from unittest.mock import patch

    conn = _DigestConn(weekly=True)
    # Lunes 18-may-2026 08:30 hora Bogotá. La semana completada es la del
    # 11–17 de mayo.
    fake_now_local = datetime(2026, 5, 18, 8, 30, tzinfo=ZoneInfo('America/Bogota'))

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fake_now_local.astimezone(tz) if tz else fake_now_local

    with patch('app.services.digest.datetime', _FakeDateTime):
        result = asyncio.run(
            build_weekly_digest(
                conn,
                tenant_id=uuid4(),
                tz_name='America/Bogota',
                currency='COP',
            )
        )
    assert result['kpis']['week_start_local'] == '2026-05-11'


def test_worker_ensures_internal_conversation_for_whatsapp_digest():
    """Bug P1 del review: `messages.conversation_id` es NOT NULL, así que el
    worker debe garantizar (contact, conversation) interna antes de encolar
    la plantilla — si inserta NULL, Postgres explota y la entrega se pierde."""
    src = Path('app/workers/digest_worker.py').read_text()
    assert '_ensure_internal_digest_conversation' in src
    # El insert ahora pasa ``conversation_id`` como parámetro, no `null`.
    assert "values ($1, $2, 'outbound'" in src
    # La conversación se marca con metadata.kind='internal_digest' para no
    # mezclar con conversaciones de clientes reales.
    assert "'kind': 'internal_digest'" in src
    # El contacto upsertea por la unique (tenant_id, wa_id) y se marca
    # ``source='internal_digest'``.
    assert "'internal_digest'" in src
    assert 'on conflict (tenant_id, wa_id)' in src


def test_wizard_renders_digest_subscriptions_panel():
    wizard = _tenant_setup_source()
    panel = _tenant_setup_source()
    assert "import DigestSubscriptionsPanel from './DigestSubscriptionsPanel.jsx'" in wizard
    assert '<DigestSubscriptionsPanel' in wizard
    # El panel vive bajo la pestaña Notificaciones (activeTab='notificaciones').
    notif_index = wizard.find("activeTab === 'notificaciones'")
    panel_index = wizard.find('<DigestSubscriptionsPanel')
    assert notif_index != -1 and panel_index > notif_index
    # El panel hace las llamadas vía coreApi.
    for name in (
        'listDigestSubscriptions',
        'createDigestSubscription',
        'updateDigestSubscription',
        'deleteDigestSubscription',
    ):
        assert name in panel
