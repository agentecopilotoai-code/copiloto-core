"""Fix-group 11: BUG-073..BUG-077.

- BUG-073: NOT-APPLICABLE — `useInboxData.handleStartConversation` ya
  flipa `setMobileView('detail')` (línea 254, codex P2 follow-up).
- BUG-074: NOT-APPLICABLE — el breakpoint mobile fue elevado a
  `max-width: 1024px` (cubre phones landscape).
- BUG-075: VIGENTE. La validación de `PATCH /me/profile` solo aceptaba
  los locales "default" por país (`es-CO`, `es-MX`, etc.). El frontend
  expone `es-ES`, `en-US`, `pt-BR` adicionales que respondían 422.
  Fix: nueva constante `SUPPORTED_USER_LOCALES` en `app/services/locale.py`
  mirroring `ACCOUNT_LOCALES` del frontend.
- BUG-076: NOT-APPLICABLE — `_validate_timezone` ya rechaza non-strings
  con 422 explícito (línea 10983).
- BUG-077: NOT-APPLICABLE — SEC-010-EXPORT-FU removió el `pg_dump`
  tenant-wide del runbook; ahora usa el endpoint contact-scoped.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import locale as locale_module
from app.api.v1 import routes as routes_module


ACCOUNT_DATA = Path('admin-panel/src/features/account/accountData.js')
RUNBOOK = Path('docs/runbooks/consent-violation-claim.md')
INBOX_HOOK = Path('admin-panel/src/features/agente/inbox/hooks/useInboxData.js')


def _source_of(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(routes_module, name)))


# ───── BUG-073 — NOT-APPLICABLE (setMobileView ya está) ──────────────────


def test_bug_073_start_conversation_flips_mobile_view_to_detail():
    src = INBOX_HOOK.read_text()
    assert "setMobileView('detail')" in src, (
        'BUG-073: regresión — `handleStartConversation` ya no flipa '
        '`mobileView=detail`. En mobile el detalle recién creado queda '
        'oculto detrás del CSS `data-mobile-view=list`.'
    )


# ───── BUG-074 — NOT-APPLICABLE (breakpoint 1024px) ──────────────────────


def test_bug_074_mobile_breakpoint_at_least_1024px():
    src = Path('admin-panel/src/app/shells/components/ShellBottomNav.module.css').read_text()
    assert '@media (max-width: 1024px)' in src, (
        'BUG-074: el media query del mobile bottom nav debe ser '
        '`max-width: 1024px` (no 768px) — phones modernos en landscape '
        'tienen >768px de viewport.'
    )


# ───── BUG-075 — SUPPORTED_USER_LOCALES whitelist extendida ──────────────


def test_bug_075_supported_user_locales_constant_exists():
    assert hasattr(locale_module, 'SUPPORTED_USER_LOCALES'), (
        'BUG-075: `app/services/locale.py` debe exponer la constante '
        '`SUPPORTED_USER_LOCALES` (frozenset) — fuente de verdad del set '
        'que valida `PATCH /me/profile`.'
    )
    assert isinstance(locale_module.SUPPORTED_USER_LOCALES, frozenset), (
        'BUG-075: debe ser `frozenset` (inmutable) para que no se mute en '
        'runtime accidentalmente.'
    )


def test_bug_075_supported_locales_include_account_locales_options():
    """El set backend debe incluir TODOS los locales que el frontend
    expone (ACCOUNT_LOCALES). Sin esto, PATCH /me/profile rechaza
    opciones legítimas con 422.
    """
    expected = {'es-CO', 'es-MX', 'es-ES', 'en-US', 'pt-BR'}
    assert expected.issubset(locale_module.SUPPORTED_USER_LOCALES), (
        f'BUG-075: SUPPORTED_USER_LOCALES debe incluir todas las opciones '
        f'expuestas por ACCOUNT_LOCALES en el frontend. Faltan: '
        f'{expected - locale_module.SUPPORTED_USER_LOCALES}'
    )


def test_bug_075_patch_profile_uses_extended_locale_set():
    full_src = inspect.getsource(routes_module)
    assert 'SUPPORTED_USER_LOCALES' in full_src, (
        'BUG-075: el handler PATCH /me/profile debe usar '
        '`SUPPORTED_USER_LOCALES` (no `default_locale(code) for code in '
        'SUPPORTED_COUNTRIES` que excluye es-ES/en-US/pt-BR).'
    )


def test_bug_075_account_locales_frontend_lists_supported_options():
    """El frontend `ACCOUNT_LOCALES` debe ser consistente con el set
    backend. Si alguien agrega una opción al frontend sin actualizar
    `SUPPORTED_USER_LOCALES`, este test catchea la divergencia
    indirectamente (los users seleccionarán la opción y PATCH falla 422).
    """
    src = ACCOUNT_DATA.read_text()
    for value in ('es-CO', 'es-MX', 'es-ES', 'en-US', 'pt-BR'):
        assert f"value: '{value}'" in src, (
            f'BUG-075: ACCOUNT_LOCALES frontend debe incluir '
            f"`{{ value: '{value}', ... }}` — si lo removés del frontend, "
            f'también removelo de `SUPPORTED_USER_LOCALES` para mantener '
            f'sync.'
        )


# ───── BUG-076 — NOT-APPLICABLE (timezone validation) ───────────────────


def test_bug_076_validate_timezone_rejects_non_string():
    src = _source_of('_validate_timezone')
    assert 'isinstance(tz, str)' in src, (
        'BUG-076: `_validate_timezone` debe rechazar non-string inputs '
        'con 422 explícito (antes pasaba a `ZoneInfo` y reventaba 500).'
    )
    assert 'timezone must be a string' in src, (
        'BUG-076: el detail del 422 debe ser específico para que el '
        'cliente sepa qué corregir.'
    )


# ───── BUG-077 — NOT-APPLICABLE (runbook usa endpoint contact-scoped) ───


def test_bug_077_runbook_uses_contact_scoped_endpoint_not_pg_dump():
    src = RUNBOOK.read_text()
    # No debe quedar instrucción de `pg_dump` para extractos.
    assert 'pg_dump --data-only --table=' not in src, (
        'BUG-077: regresión — el runbook volvió a recomendar `pg_dump` '
        'para extractos. Usar el endpoint contact-scoped SEC-010-EXPORT-FU.'
    )
    # Debe linkear al endpoint nuevo.
    assert '/contacts/<contact_id>/export' in src, (
        'BUG-077: el runbook debe documentar `curl` al endpoint contact-scoped '
        '(`GET /v1/tenants/<tenant_id>/contacts/<contact_id>/export`).'
    )
