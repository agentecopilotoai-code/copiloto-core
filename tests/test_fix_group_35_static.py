"""Fix-group 35: Codex Security HIGH findings — Auth0/authn cluster.

Cierra 4 findings del CSV `codex-security-findings-2026-05-18T12-29-09.086Z.csv`:

- **BUG-193** (HIGH, `app/services/auth0_admin.py`): `lookup_auth0_user_by_email`
  reutiliza `response[0]` sin chequear (a) `email_verified=true` ni (b) que
  hay un único match. Auth0 permite múltiples cuentas con el mismo email
  cross-connection (database + Google OAuth + LinkedIn). Un atacante puede
  registrar una cuenta sin verificar y secuestrar el invite cuando un admin
  invita a la víctima.
- **BUG-194** (HIGH, `scripts/configure-auth0.sh`): el bootstrap del
  platform_owner no verificaba `email_verified=true` antes de asignar el
  rol más privilegiado del sistema. Un atacante que registre el email del
  owner antes que la víctima recibe `platform_owner` + `support_mode`.
- **BUG-195** (HIGH, `app/api/v1/routes.py`): `user_email_from_request`
  hacía fallback al header `X-Admin-User-Email` cuando el JWT no traía
  claim `email`. Un caller con bearer token directo podía spoofear el
  email storage de su propia row `app.users`. Después, al invitar a la
  víctima por email, el invite reutilizaba la row spoofeada → el atacante
  hereda la membresía.
- **BUG-196** (HIGH, `app/admin/routes.py` + `app/services/auth0_admin.py`):
  el WS endpoint `_session_can_stream_tenant` aceptaba el stream si el
  claim `tenant_id` cacheado en la sesión BFF matcheaba — no DB-checkeaba
  contra `app.user_tenant_roles`. Después de revocar a un user, el WS
  seguía activo hasta que expirara la sesión. Además `revoke_tenant_roles`
  no limpiaba `app_metadata.tenant_id` / `default_tenant_id`, así que el
  siguiente login aún traía el claim al tenant revocado.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


AUTH0_ADMIN = Path('app/services/auth0_admin.py')
CONFIGURE_AUTH0 = Path('scripts/configure-auth0.sh')
ADMIN_ROUTES = Path('app/admin/routes.py')


# ───── BUG-193 — lookup_auth0_user_by_email enforce single + verified ────


def test_bug_193_lookup_defines_ambiguous_match_exception():
    src = AUTH0_ADMIN.read_text()
    assert 'class Auth0AmbiguousUserMatch(Exception):' in src, (
        'BUG-193: debe existir `Auth0AmbiguousUserMatch` para el caso de '
        'múltiples cuentas Auth0 con el mismo email.'
    )


def test_bug_193_lookup_defines_unverified_exception():
    src = AUTH0_ADMIN.read_text()
    assert 'class Auth0UserNotVerified(Exception):' in src, (
        'BUG-193: debe existir `Auth0UserNotVerified` para el caso de '
        'cuenta Auth0 sin `email_verified=true`.'
    )


def test_bug_193_lookup_enforces_single_match_by_default():
    src = AUTH0_ADMIN.read_text()
    fn_idx = src.find('async def lookup_auth0_user_by_email(')
    assert fn_idx > 0
    next_fn = src.find('\nasync def ', fn_idx + 1)
    block = src[fn_idx:next_fn]
    assert 'enforce_single: bool = True' in block, (
        'BUG-193: `lookup_auth0_user_by_email` debe aceptar `enforce_single` '
        'con default True.'
    )
    assert 'raise Auth0AmbiguousUserMatch(' in block, (
        'BUG-193: cuando hay >1 match y `enforce_single`, debe levantar '
        '`Auth0AmbiguousUserMatch`.'
    )


def test_bug_193_lookup_enforces_email_verified_by_default():
    src = AUTH0_ADMIN.read_text()
    fn_idx = src.find('async def lookup_auth0_user_by_email(')
    next_fn = src.find('\nasync def ', fn_idx + 1)
    block = src[fn_idx:next_fn]
    assert 'require_email_verified: bool = True' in block, (
        'BUG-193: `lookup_auth0_user_by_email` debe aceptar '
        '`require_email_verified` con default True.'
    )
    assert 'raise Auth0UserNotVerified(' in block, (
        'BUG-193: cuando el match tiene `email_verified=false` y '
        '`require_email_verified`, debe levantar `Auth0UserNotVerified`.'
    )


def test_bug_193_invite_route_handles_new_exceptions():
    src = routes_aggregated_source()
    assert 'Auth0AmbiguousUserMatch' in src, (
        'BUG-193: `routes.py` debe importar `Auth0AmbiguousUserMatch` para '
        'mapearlo a un HTTP 409 con mensaje de desambiguación.'
    )
    assert 'Auth0UserNotVerified' in src, (
        'BUG-193: `routes.py` debe importar `Auth0UserNotVerified` para '
        'mapearlo a un HTTP 403 con mensaje pidiendo verificación de email.'
    )
    assert 'except Auth0AmbiguousUserMatch' in src, (
        'BUG-193: el invite handler debe capturar `Auth0AmbiguousUserMatch`.'
    )
    assert 'except Auth0UserNotVerified' in src, (
        'BUG-193: el invite handler debe capturar `Auth0UserNotVerified`.'
    )


# ───── BUG-194 — bootstrap script email_verified ─────────────────────────


def test_bug_194_bootstrap_checks_email_verified():
    src = CONFIGURE_AUTH0.read_text()
    assert "bootstrap_user_verified=\"$(jq -r '.[0].email_verified // false'" in src, (
        'BUG-194: el bootstrap de `configure-auth0.sh` debe extraer '
        '`email_verified` del response de `/users-by-email`.'
    )
    assert 'if [ "$bootstrap_user_verified" != "true" ]; then' in src, (
        'BUG-194: el bootstrap debe abortar si `email_verified != true` '
        'antes de asignar el rol `platform_owner`.'
    )


# ───── BUG-195 — user_email_from_request drops header trust ──────────────


def test_bug_195_user_email_from_request_does_not_trust_header():
    src = routes_aggregated_source()
    fn_idx = src.find('def user_email_from_request(request: Request) -> str:')
    assert fn_idx > 0
    next_fn = src.find('\ndef user_display_name_from_request', fn_idx)
    block = src[fn_idx:next_fn]
    assert "request.headers.get('X-Admin-User-Email')" not in block, (
        'BUG-195: `user_email_from_request` NO debe usar el header '
        '`X-Admin-User-Email` como fallback para el email canónico — '
        'puede ser spoofeado por un caller con bearer token directo.'
    )
    # Debe seguir aceptando el email del JWT (request.state.email).
    assert "getattr(request.state, 'email', None)" in block, (
        'BUG-195: `user_email_from_request` debe consumir el email del JWT '
        '(`request.state.email`, populado por `authenticate_request`).'
    )


# ───── BUG-196 — WS DB-check + revoke clears app_metadata tenant pointer ─


def test_bug_196_session_can_stream_tenant_drops_claim_shortcut():
    src = ADMIN_ROUTES.read_text()
    fn_idx = src.find('async def _session_can_stream_tenant(')
    assert fn_idx > 0
    next_fn = src.find('\ndef _active_session(', fn_idx)
    block = src[fn_idx:next_fn]
    # El shortcut viejo `_session_claim_matches_tenant(session, tenant_id)`
    # NO debe estar (sin esto el revoke nunca llegaba a producir efecto WS).
    assert '_session_claim_matches_tenant(session, tenant_id)' not in block, (
        'BUG-196: `_session_can_stream_tenant` NO debe trustear el claim '
        '`tenant_id` cacheado del JWT — debe DB-checkear '
        '`app.user_tenant_roles` AHORA.'
    )
    # El DB-check sigue presente.
    assert 'app.user_tenant_roles' in block, (
        'BUG-196: el DB-check contra `app.user_tenant_roles` debe seguir '
        'siendo el path autoritativo del WS gate.'
    )


def test_bug_196_revoke_tenant_roles_clears_stale_tenant_pointer():
    src = AUTH0_ADMIN.read_text()
    fn_idx = src.find('async def revoke_tenant_roles(')
    assert fn_idx > 0
    # Buscar el final aproximado de la función.
    next_def = src.find('\nasync def ', fn_idx + 1)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:]
    # Lee el app_metadata actual para comparar contra el tenant revocado.
    assert "current_app_meta" in block, (
        'BUG-196: `revoke_tenant_roles` debe leer el `app_metadata` actual '
        'del user para comparar `tenant_id` / `default_tenant_id`.'
    )
    # Nullify si matchea.
    assert "patch_app_meta['tenant_id'] = None" in block, (
        'BUG-196: si el `tenant_id` actual matchea el tenant revocado, '
        'el revoke debe nullificarlo en `app_metadata`.'
    )
    assert "patch_app_meta['default_tenant_id'] = None" in block, (
        'BUG-196: ídem para `default_tenant_id`.'
    )
