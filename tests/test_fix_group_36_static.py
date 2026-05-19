"""Fix-group 36: Codex Security HIGH+MEDIUM — support-mode/sessions/audit/go-live.

Cierra 4 findings:

- **BUG-197** (HIGH, `app/api/v1/routes.py:11648`): `POST /me/support-mode/{tenant_id}`
  permitía a un `platform_owner` activar el cookie cross-tenant SIN haber
  pasado MFA. La matriz de privilegios (TASK-0080) marca cross-tenant access
  como uno de los actions más sensibles del sistema; debe requerir MFA por
  diseño.
- **BUG-198** (MEDIUM, `app/api/v1/routes.py:11750`): `DELETE /me/support-mode/{tenant_id}`
  llamaba `audit_durably` con el `tenant_id` del path para CUALQUIER auth user
  — sin verificar que el cookie matchea. `audit_durably` setea
  `app.tenant_id=<path>` en una conn fresca, pasando la RLS de
  `audit_logs_tenant_insert` (que solo exige tenant match, no rol del actor).
  Resultado: cualquier user autenticado podía polucionar el audit log de un
  tenant víctima con `support_mode.deactivated` falsos.
- **BUG-199** (MEDIUM, `app/core/security.py:288`): `authenticate_request`
  no consultaba `app.auth_sessions.revoked_at`. Una sesión revocada desde la
  UI seguía aceptando requests hasta que expirara el JWT (8-24h). El user
  creía haber cerrado una sesión comprometida y la API seguía aceptándola.
- **BUG-200** (MEDIUM, `app/api/v1/routes.py:2884`): `POST /v1/tenants/{id}/go-live`
  usaba `require_min_role('owner')` que acepta `owner` y `platform_owner`
  (rank superior). `ensure_tenant_access` además bypassea para `platform_owner`
  en support_mode. La UI no le da `mark_live` a esos roles — pero el backend
  no cerraba el bypass. Fix: DB-check explícito que el actor tenga
  `role='owner'` en `user_tenant_roles` para el tenant target.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


SECURITY = Path('app/core/security.py')


# ───── BUG-197 — MFA en support-mode activation ──────────────────────────


def test_bug_197_activate_support_mode_requires_mfa():
    src = routes_aggregated_source()
    decorator_start = src.find("@me_router.post(\n    '/me/support-mode/{tenant_id}'")
    assert decorator_start > 0, (
        'BUG-197: el decorator de `activate_support_mode` debe ser multi-line '
        'para incluir `dependencies=[Depends(require_mfa_for_privileged)]`.'
    )
    decorator_end = src.find(')\nasync def activate_support_mode(', decorator_start)
    decorator_block = src[decorator_start:decorator_end + 1]
    assert 'dependencies=[Depends(require_mfa_for_privileged)]' in decorator_block, (
        'BUG-197: `activate_support_mode` debe declarar '
        '`dependencies=[Depends(require_mfa_for_privileged)]` para forzar MFA '
        'antes de habilitar el opt-in cross-tenant.'
    )


# ───── BUG-198 — DELETE support-mode audit solo si cookie matchea ────────


def test_bug_198_deactivate_only_audits_when_cookie_matches():
    src = routes_aggregated_source()
    fn_idx = src.find('async def deactivate_support_mode(')
    assert fn_idx > 0
    # Buscar el siguiente def para acotar el bloque.
    next_def = src.find('\nweb_router = ', fn_idx)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:]
    # Debe leer el cookie y validar tid + sub.
    assert "request.cookies.get(SUPPORT_MODE_COOKIE_NAME)" in block, (
        'BUG-198: el DELETE debe leer el cookie `SUPPORT_MODE_COOKIE_NAME` '
        'antes de auditar.'
    )
    assert 'unpack_signed_payload(settings.jwt_secret, cookie_value)' in block, (
        'BUG-198: el DELETE debe desempaquetar el cookie firmado para validar '
        'que `tid` matchea el `tenant_id` del path Y `sub` matchea el JWT.'
    )
    # El audit_durably debe estar gateado por la variable cookie_matches_request.
    assert 'cookie_matches_request = False' in block, (
        'BUG-198: debe existir una variable de control `cookie_matches_request` '
        'que arranque en False.'
    )
    assert 'if cookie_matches_request:' in block, (
        'BUG-198: el `audit_durably(...)` debe estar dentro de '
        '`if cookie_matches_request:`. Sin esto cualquier auth user audita '
        'una deactivation falsa para el tenant víctima.'
    )


# ───── BUG-199 — authenticate_request consulta auth_sessions.revoked_at ──


def test_bug_199_authenticate_enforces_session_revocation():
    src = SECURITY.read_text()
    fn_idx = src.find('async def authenticate_request(')
    assert fn_idx > 0
    # Buscar el siguiente def para acotar el bloque.
    next_def = src.find('\ndef _derive_session_id(', fn_idx)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:fn_idx + 4000]
    # Debe invocar el helper de revocación al final de authenticate_request.
    assert '_enforce_session_not_revoked(' in block, (
        'BUG-199: `authenticate_request` debe llamar '
        '`_enforce_session_not_revoked(session_id)` después de poblar '
        '`request.state.session_jti`.'
    )


def test_bug_199_enforce_helper_queries_revoked_at():
    src = SECURITY.read_text()
    fn_idx = src.find('async def _enforce_session_not_revoked(')
    assert fn_idx > 0, (
        'BUG-199: debe existir el helper `_enforce_session_not_revoked` en '
        '`security.py`.'
    )
    next_def = src.find('\ndef _has_role(', fn_idx)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:fn_idx + 1500]
    assert 'app.auth_sessions' in block and 'revoked_at' in block, (
        'BUG-199: el helper debe consultar `app.auth_sessions.revoked_at` '
        'para el `session_id` derivado del JWT.'
    )
    assert "raise HTTPException(" in block and "401" in block.replace("status.HTTP_401_UNAUTHORIZED", "401"), (
        'BUG-199: cuando `revoked_at IS NOT NULL` el helper debe levantar 401.'
    )


# ───── BUG-200 — go-live exige DB role owner ─────────────────────────────


def test_bug_200_go_live_requires_db_owner_role():
    src = routes_aggregated_source()
    fn_idx = src.find('async def mark_tenant_go_live(')
    if fn_idx == -1:
        # Otro nombre posible — buscar por path en decorator.
        fn_idx = src.find("/go-live'")
        assert fn_idx > 0, 'BUG-200: no encontré el handler de go-live'
    # Buscar el bloque entre la declaración y el siguiente def.
    block_start = src.rfind('@', 0, fn_idx)
    next_def = src.find('\n@', block_start + 1)
    block = src[block_start:next_def] if next_def > 0 else src[block_start:block_start + 6000]
    # Debe haber un fetch sobre user_tenant_roles con role='owner'.
    assert "utr.role = 'owner'" in block, (
        "BUG-200: el handler de go-live debe DB-checkear que el actor tiene "
        "row con `utr.role = 'owner'` en `app.user_tenant_roles` para el "
        "tenant_id target — NO confiar solo en `require_min_role('owner')` "
        "(que acepta platform_owner) ni en `ensure_tenant_access` (que tiene "
        "bypass para support_mode)."
    )
    # Debe haber un raise 403 explícito con el mensaje de bypass denegado.
    assert 'platform_owner / support_mode bypass is not honored' in block, (
        'BUG-200: el error 403 debe explicitar que el bypass de platform_owner '
        '/ support_mode no aplica a go-live.'
    )
