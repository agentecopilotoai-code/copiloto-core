"""Fix-group 20: BUG-118..BUG-122.

- BUG-118: VIGENTE. FleetDlq.enterTenant pasaba `{...tenant}` a
  `handleTenantCreated`; las rows del fleet DLQ solo tienen
  `tenant_id` (no `id`), así que TenantProvider guardaba
  `{id: undefined, ...}` y los lookups downstream rompían. Fix: spread
  + `id: tenant.tenant_id` explícito.
- BUG-119: VIGENTE. `/platform/incidents` devolvía el payload raw de
  `operator_alerts`, incluyendo PII de contactos (contact_phone, name,
  email) y los canales de notificación del operador (emails/whatsapp).
  Fix: `platform_incidents.redact_incident_payload(payload)` aplica
  máscara antes de devolver.
- BUG-120: VIGENTE. La MRR query por plan filtraba `where sp.status =
  'active'`, ocultando planes archivados con subs activas (archive es
  forward-only — los contracts existentes siguen facturándose). Fix:
  remover el filtro + `having count(active|past_due) > 0` + exponer
  `plan_status` en la respuesta para que la UI decore.
- BUG-121: VIGENTE. `build_outstanding_alerts` solo paginaba al cruzar
  queue > 1000; el rango 101-1000 quedaba silente. Fix: alerta warning
  `SchedulerBehind` para 100 < queue ≤ 1000.
- BUG-122: VIGENTE. `outbound_failed` sumaba `failed + rejected`;
  rejected (opt-out, ventana vencida, template inválido) no es un
  error transitorio y inflaba `outbound_error_rate` con alertas
  falsas de `HighOutboundErrorRate`. Fix: split — `outbound_failed`
  solo cuenta `failed`; `outbound_rejected` se expone aparte.
"""
from __future__ import annotations

from pathlib import Path


FLEET_DLQ = Path('admin-panel/src/features/platform/fleet-dlq/FleetDlq.jsx')
PLATFORM_INCIDENTS = Path('app/services/platform_incidents.py')
ROUTES = Path('app/api/v1/routes.py')
METRICS = Path('app/services/metrics.py')


# ───── BUG-118 — FleetDlq pasa `id` explícito ────────────────────────────


def test_bug_118_fleet_dlq_enter_tenant_maps_id_from_tenant_id():
    src = FLEET_DLQ.read_text()
    # El spread original guardaba `{id: undefined, tenant_id: '...', ...}`.
    # Tras el fix, el call incluye `id: tenant.tenant_id` explícito.
    enter_idx = src.find('function enterTenant(')
    assert enter_idx > 0
    next_brace = src.find('\n  }\n', enter_idx)
    block = src[enter_idx:next_brace]
    assert 'handleTenantCreated' in block
    assert 'id: tenant.tenant_id' in block, (
        'BUG-118: `enterTenant` debe pasar `id: tenant.tenant_id` explícito al '
        '`handleTenantCreated` — sin esto el TenantProvider guardaba '
        '`{id: undefined, ...}` y los lookups por `option.id` se rompían.'
    )


# ───── BUG-119 — redactor de PII en incidents payload ────────────────────


def test_bug_119_platform_incidents_module_exports_redact_helper():
    src = PLATFORM_INCIDENTS.read_text()
    assert 'def redact_incident_payload(' in src, (
        'BUG-119: `platform_incidents.redact_incident_payload(payload)` debe '
        'existir como entry-point del redactor.'
    )
    # Debe cubrir las keys obvias de PII: phone, email, name, recipient_*.
    for sensitive_key in (
        "'contact_phone'",
        "'contact_name'",
        "'recipient_email'",
        "'recipient_whatsapp'",
    ):
        assert sensitive_key in src, (
            f'BUG-119: la lista de keys sensibles debe incluir {sensitive_key}.'
        )
    # El redactor debe colapsar `channels` a `email_count`/`whatsapp_count`.
    assert "'email_count'" in src and "'whatsapp_count'" in src, (
        'BUG-119: el bloque `channels` debe reducirse a counts (no exponer '
        'los emails/whatsapp del operador).'
    )


def test_bug_119_incidents_route_invokes_redact():
    src = ROUTES.read_text()
    # El route del feed debe envolver el payload con el redactor.
    feed_idx = src.find("@platform_admin_router.get('/platform/incidents')")
    assert feed_idx > 0
    next_route = src.find('@', feed_idx + 10)
    block = src[feed_idx:next_route]
    assert 'platform_incidents.redact_incident_payload(' in block, (
        'BUG-119: la route `/platform/incidents` debe envolver el `payload` '
        'con `platform_incidents.redact_incident_payload(...)` antes de '
        'devolverlo al platform_owner.'
    )


def test_bug_119_redact_payload_unit_behaviour():
    """Smoke unitario del redactor."""
    from app.services.platform_incidents import redact_incident_payload
    out = redact_incident_payload({
        'contact_phone': '+573001234567',
        'contact_name': 'María González',
        'recipient_email': 'agent@empresa.com',
        'summary': 'Cliente reportó queja',
        'channels': {
            'emails': ['op1@x.com', 'op2@x.com'],
            'whatsapps': ['+1', '+2', '+3'],
        },
        'nested': {'contact_phone': '+9'},
    })
    assert '[redacted' in out['contact_phone']
    assert '[redacted' in out['contact_name']
    assert '[redacted' in out['recipient_email']
    assert out['summary'] == 'Cliente reportó queja'
    assert out['channels'] == {'email_count': 2, 'whatsapp_count': 3}
    assert '[redacted' in out['nested']['contact_phone']
    # Empty / non-dict input degrada limpiamente.
    assert redact_incident_payload(None) == {}
    assert redact_incident_payload('not a dict') == {}


# ───── BUG-120 — plans archivados con subs activas en MRR ────────────────


def test_bug_120_mrr_plan_query_includes_archived_plans_with_active_subs():
    src = ROUTES.read_text()
    mrr_idx = src.find("@platform_admin_router.get('/platform/billing/mrr')")
    assert mrr_idx > 0
    next_route = src.find('@platform_admin_router', mrr_idx + 10)
    block = src[mrr_idx:next_route]
    # El `where sp.status = 'active'` (en SQL, con leading whitespace) debe
    # haberse removido — el match suelto seguiría disparando por el comentario
    # explicativo del fix.
    assert "        where sp.status = 'active'" not in block, (
        "BUG-120: el `where sp.status = 'active'` filtra fuera los planes "
        "archivados que todavía tienen suscriptores pagando. Debe removerse y "
        "usar un `having count(...) > 0` para mostrar solo planes con subs."
    )
    assert "having count(cs.id) filter (where cs.status in ('active', 'past_due')) > 0" in block, (
        'BUG-120: la query por plan debe terminar con `having count(...active|past_due) > 0` '
        'para mostrar solo planes con suscriptores actuales (sin importar el plan_status).'
    )
    assert "sp.status as plan_status" in block, (
        'BUG-120: la query debe incluir `sp.status as plan_status` para que la UI '
        'pueda decorar visualmente los planes archivados.'
    )
    assert "'plan_status': row['plan_status']" in block, (
        'BUG-120: la response debe propagar `plan_status` por plan.'
    )


# ───── BUG-121 — SchedulerBehind warning entre 100-1000 ──────────────────


def test_bug_121_scheduler_behind_warning_alert_present():
    src = METRICS.read_text()
    assert "'SchedulerBehind'" in src, (
        'BUG-121: debe existir un alert `SchedulerBehind` para el rango '
        '101-1000 (antes solo paginábamos a >1000, el rango intermedio '
        'quedaba silente aunque indica scheduler atrasado).'
    )
    # Asegurar que es severity warning (no page) — el page sigue siendo >1000.
    sb_idx = src.find("'SchedulerBehind'")
    block_end = src.find('})', sb_idx)
    block = src[sb_idx:block_end]
    assert "'severity': 'warning'" in block, (
        'BUG-121: `SchedulerBehind` debe ser severity warning (no page). '
        'El page sigue siendo `WorkerQueueBacklog` para >1000.'
    )


def test_bug_121_worker_queue_backlog_still_pages_at_1000():
    """Defensa anti-regresión: el page de >1000 sigue ahí."""
    src = METRICS.read_text()
    assert "'WorkerQueueBacklog'" in src
    wq_idx = src.find("'WorkerQueueBacklog'")
    block_end = src.find('})', wq_idx)
    block = src[wq_idx:block_end]
    assert "'severity': 'page'" in block, (
        'Regresión BUG-121: `WorkerQueueBacklog` debe seguir siendo `page`.'
    )


# ───── BUG-122 — rejected separado de failed ─────────────────────────────


def test_bug_122_outbound_failed_excludes_rejected():
    src = METRICS.read_text()
    # El antiguo bundle ('failed', 'rejected') ya no debe existir.
    assert "status in ('failed', 'rejected')" not in src, (
        'BUG-122: `outbound_failed` no debe bundlear `rejected`. Esa mezcla '
        'inflaba `outbound_error_rate` con alertas falsas de '
        '`HighOutboundErrorRate` cada vez que el bot rechazaba mensajes por '
        'opt-out / ventana vencida / template inválida.'
    )
    # El nuevo split debe estar presente.
    assert "status == 'failed'" in src and "status == 'rejected'" in src, (
        "BUG-122: ahora `outbound_failed` filtra solo `status == 'failed'` "
        "y `outbound_rejected` se cuenta aparte para visibilidad sin paginar."
    )


def test_bug_122_outbound_rejected_exposed_in_snapshot():
    src = METRICS.read_text()
    assert "'outbound_rejected': int(outbound_rejected)" in src, (
        'BUG-122: el snapshot debe exponer `outbound_rejected` como campo '
        'separado para que los operadores vean el volumen sin que entre al '
        'error_rate.'
    )
