"""BUG-008 — toggle opt-in temporal de `support_mode` para `platform_owner`.

Reemplaza el workaround de `BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE=true` en
Auth0 (modo permanente) por un opt-in scoped por tenant con TTL y audit.

Surface a defender:

1. Helper genérico `app/core/signed_cookies.py` — wire format HMAC-SHA256 +
   base64url, roundtrip, tamper detection.
2. Endpoints `POST /v1/me/support-mode/{tenant_id}` y `DELETE /v1/me/support-mode/{tenant_id}`
   en `me_router` con:
   - Auth `platform_owner` (rol global) — sin esto, 403.
   - Validación de tenant existe.
   - Cookie firmado scoped al tenant_id + user sub.
   - Audit log `support_mode.activated` / `support_mode.deactivated` durable.
3. `authenticate_request` lee el cookie SOLO si la request manda `X-Tenant-Id`
   matcheando el `tid` del cookie Y el `sub` del JWT matchea el del cookie
   Y el `exp` del cookie no expiró.
4. `request.state.support_mode_source` distingue 'jwt' / 'cookie' / 'service'
   / None para audit y debug.

Si cualquier invariante se rompe, este test falla loudly antes de mergear.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.core import security as security_module
from app.core.signed_cookies import (
    pack_signed_payload,
    unpack_signed_payload,
)

ROUTES = Path('app/api/v1/routes.py')
SECURITY = Path('app/core/security.py')
SIGNED_COOKIES = Path('app/core/signed_cookies.py')
ADMIN_ROUTES = Path('app/admin/routes.py')


# ───── Helper genérico signed_cookies ────────────────────────────────────


def test_signed_cookies_roundtrip_basic():
    """El helper debe poder serializar + deserializar un payload arbitrario
    sin alterar los campos.
    """
    secret = 'x' * 32
    payload = {'sub': 'u-1', 'tid': 'abc', 'exp': 12345, 'iat': 12000}
    cookie = pack_signed_payload(secret, payload)
    decoded = unpack_signed_payload(secret, cookie)
    assert decoded == payload


def test_signed_cookies_tamper_detection():
    """Cambiar UN char del cookie debe invalidarlo. Constant-time compare
    via `hmac.compare_digest` previene timing side channels.
    """
    secret = 'x' * 32
    cookie = pack_signed_payload(secret, {'sub': 'u-1', 'tid': 'abc'})
    # Tampering del payload (cambia el carácter del medio).
    tampered = cookie[:5] + ('Z' if cookie[5] != 'Z' else 'Y') + cookie[6:]
    assert unpack_signed_payload(secret, tampered) is None


def test_signed_cookies_wrong_secret_rejected():
    """Un cookie firmado con secret A no debe validar bajo secret B."""
    cookie = pack_signed_payload('secret-a' * 4, {'a': 1})
    assert unpack_signed_payload('secret-b' * 4, cookie) is None


def test_signed_cookies_malformed_value_returns_none():
    """Inputs que no respetan el formato `<b64url>.<b64url>` deben
    devolver None — NUNCA raise. El caller (authenticate_request) no
    debe romperse por un cookie corrupto que el usuario mandó.
    """
    secret = 'x' * 32
    assert unpack_signed_payload(secret, '') is None
    assert unpack_signed_payload(secret, 'nodot') is None
    assert unpack_signed_payload(secret, 'abc.def.ghi') is None
    assert unpack_signed_payload(secret, '.') is None


def test_signed_cookies_uses_hmac_compare_digest():
    """Constant-time comparison — defensa frontal contra timing side
    channels. AST-based para que un refactor accidental no use `==`.
    """
    src = SIGNED_COOKIES.read_text()
    tree = ast.parse(src)
    found_compare_digest = any(
        isinstance(node, ast.Attribute)
        and node.attr == 'compare_digest'
        and isinstance(node.value, ast.Name)
        and node.value.id == 'hmac'
        for node in ast.walk(tree)
    )
    assert found_compare_digest, (
        'unpack_signed_payload debe usar hmac.compare_digest para evitar '
        'timing oracle sobre el HMAC'
    )


def test_admin_routes_migrated_to_shared_helper():
    """`app/admin/routes.py` (OAuth state cookie) debe reusar el helper
    compartido para que no haya dos implementaciones del wire format.
    Si alguien re-inline-a un `_pack_state` local, los dos consumers se
    pueden desincronizar silenciosamente.
    """
    src = ADMIN_ROUTES.read_text()
    assert 'from app.core.signed_cookies import' in src, (
        'admin/routes.py debe importar del helper compartido'
    )
    # Las funciones locales son wrappers (delegan al helper).
    assert 'pack_signed_payload(settings.state_secret, payload)' in src
    assert 'unpack_signed_payload(settings.state_secret, value)' in src


# ───── authenticate_request lee cookie scoped ────────────────────────────


def test_security_exposes_support_mode_cookie_name_constant():
    """El nombre del cookie es público para que el endpoint POST + tests
    apunten al mismo string. Sin esto, un typo en un lado deja el cookie
    "huérfano" que nadie lee.
    """
    assert hasattr(security_module, 'SUPPORT_MODE_COOKIE_NAME')
    assert security_module.SUPPORT_MODE_COOKIE_NAME == 'copilotoia_support_mode'


def test_authenticate_request_reads_support_mode_cookie():
    """El handler `authenticate_request` debe leer el cookie cuando
    NO hay support_mode en el JWT pero SÍ hay `X-Tenant-Id`. Sin esto,
    el toggle del frontend nunca aplica.
    """
    src = inspect.getsource(security_module.authenticate_request)
    assert 'SUPPORT_MODE_COOKIE_NAME' in src
    assert 'request.cookies.get(SUPPORT_MODE_COOKIE_NAME)' in src
    assert 'unpack_signed_payload(settings.jwt_secret, cookie_value)' in src


def test_authenticate_request_validates_cookie_scope():
    """El cookie debe matchear:
      - `tid` == str(X-Tenant-Id) del request — scoped al tenant.
      - `sub` == JWT payload['sub'] — atado al user (no se reusa entre users).
      - `exp` > now — TTL respetado.
    Si cualquiera falla, el bumpeo de support_mode NO ocurre.
    """
    src = inspect.getsource(security_module.authenticate_request)
    assert "cookie_tid == str(x_tenant_id)" in src
    assert "cookie_sub == payload.get('sub')" in src
    assert 'cookie_exp > now_ts' in src


def test_authenticate_request_sets_support_mode_source():
    """`request.state.support_mode_source` distingue cómo se activó el modo.
    Útil para audit (queremos saber si la acción ocurrió bajo opt-in temporal
    o bajo el modo permanente legacy).
    """
    src = inspect.getsource(security_module.authenticate_request)
    # Inicialización para anonymous.
    assert 'request.state.support_mode_source = None' in src
    # Service token tag.
    assert "request.state.support_mode_source = 'service'" in src
    # Final assignment después del cookie check.
    assert 'request.state.support_mode_source = support_mode_source' in src


def test_authenticate_request_only_reads_cookie_when_no_jwt_support_mode():
    """Optimización + clarity: el cookie solo se evalúa cuando el JWT NO
    trae support_mode=true. Si el JWT ya lo trae permanente (legacy), no
    necesitamos parsear el cookie.
    """
    src = inspect.getsource(security_module.authenticate_request)
    # El guard es `if not support_mode and x_tenant_id:`
    assert 'if not support_mode and x_tenant_id:' in src


# ───── Endpoints POST/DELETE /me/support-mode/{tenant_id} ────────────────


def test_activate_support_mode_endpoint_exists_in_me_router():
    """Endpoint montado en me_router (heredando authenticate_request)."""
    assert hasattr(routes_module, 'activate_support_mode')
    assert hasattr(routes_module, 'deactivate_support_mode')


def test_activate_support_mode_requires_platform_owner():
    """Sin rol global `platform_owner`, el endpoint debe devolver 403.
    Esto preserva la semantic de TASK-0077 — solo el rol cross-tenant
    puede pedir support_mode.
    """
    src = inspect.getsource(routes_module.activate_support_mode)
    assert "'platform_owner' not in (getattr(request.state, 'roles', []) or [])" in src
    assert 'status_code=403' in src
    assert 'platform_owner role required' in src


def test_activate_support_mode_validates_tenant_exists():
    """Antes de emitir el cookie, validar que el tenant existe — sino el
    operator queda con un cookie scoped a un UUID inexistente."""
    src = inspect.getsource(routes_module.activate_support_mode)
    assert 'select 1 from app.tenants where id=$1 and deleted_at is null' in src
    assert "raise HTTPException(status_code=404, detail='Tenant not found')" in src


def test_activate_support_mode_emits_signed_cookie_with_ttl():
    """El cookie debe ir HTTP-only, samesite=lax, con max_age=TTL_SECONDS,
    firmado con `jwt_secret`. El payload incluye `sub`, `tid`, `iat`, `exp`.
    """
    src = inspect.getsource(routes_module.activate_support_mode)
    assert 'pack_signed_payload(settings.jwt_secret, cookie_payload)' in src
    assert 'response.set_cookie(' in src
    assert 'SUPPORT_MODE_COOKIE_NAME' in src
    assert 'httponly=True' in src
    assert "samesite='lax'" in src
    assert 'max_age=SUPPORT_MODE_TTL_SECONDS' in src
    # `secure=True` en producción, False en local (cookies secure no se
    # mandan sobre http, lo que rompería dev). El gate es `app_env != 'local'`.
    assert "settings.app_env != 'local'" in src


def test_activate_support_mode_audits_durably():
    """audit_durably (no audit) para que el log sobreviva si el handler
    falla post-emit del cookie (SEC-010 fix reusado).
    """
    src = inspect.getsource(routes_module.activate_support_mode)
    assert 'await audit_durably(' in src
    assert "action='support_mode.activated'" in src
    # Metadata incluye lo necesario para forensia.
    assert "'expires_at'" in src
    assert "'ttl_seconds'" in src
    assert "'justification'" in src


def test_deactivate_support_mode_deletes_cookie_and_audits():
    """DELETE es idempotente — siempre 204 (el cliente no necesita
    diferenciar 'no había cookie' de 'borrado exitoso'). Audit log siempre
    para detectar patrones repetitivos activate/deactivate.
    """
    src = inspect.getsource(routes_module.deactivate_support_mode)
    assert 'response.delete_cookie(' in src
    assert 'SUPPORT_MODE_COOKIE_NAME' in src
    assert "action='support_mode.deactivated'" in src
    assert 'await audit_durably(' in src


# ───── Constantes operacionales ──────────────────────────────────────────


def test_ttl_is_one_hour():
    """TTL default — 1h es razonable para una sesión de soporte. Cambiar
    requiere actualización del runbook + comunicación al equipo operativo
    (audit metadata captura el valor).
    """
    assert routes_module.SUPPORT_MODE_TTL_SECONDS == 60 * 60


# ───── Source-level: no hay double-implementation del wire format ────────


def test_no_inline_hmac_signing_outside_signed_cookies_module():
    """Defensa contra que alguien re-inline-e una versión local del
    HMAC + base64url. El único lugar válido es `app/core/signed_cookies.py`
    y los wrappers en `app/admin/routes.py` que delegan a él.
    """
    routes_src = ROUTES.read_text()
    # routes.py NO debe construir HMACs a mano para support-mode cookies.
    # Acepta el import del helper compartido (los strings de import no
    # cuentan como inline).
    inline_hmac_lines = [
        line for line in routes_src.splitlines()
        if 'hmac.new(' in line and 'import' not in line
    ]
    assert not inline_hmac_lines, (
        f'routes.py tiene HMAC inline — debe usar pack_signed_payload: '
        f'{inline_hmac_lines}'
    )


# ───── codex P2: DELETE devuelve el response inyectado ───────────────────


def test_deactivate_returns_injected_response_preserving_cookie_expiry():
    """El handler hace `response.delete_cookie(...)` sobre el `response`
    inyectado por FastAPI. Si después devuelve `Response(status_code=204)`
    nuevo, los headers (incluido `Set-Cookie: Max-Age=0`) se DESCARTAN y
    el browser nunca expira el cookie. El fix: mutar `status_code` en el
    response inyectado y devolverlo tal cual.
    """
    src = inspect.getsource(routes_module.deactivate_support_mode)
    # NO debe haber `return Response(status_code=...)` con un Response nuevo.
    assert 'return Response(status_code=' not in src, (
        'deactivate_support_mode no debe construir un Response nuevo — '
        'eso descarta el Set-Cookie expiry. Usar response.status_code = ...'
    )
    # SÍ debe mutar el response inyectado.
    assert 'response.status_code = status.HTTP_204_NO_CONTENT' in src
    assert 'return response' in src


# ───── codex P1: admin proxy forwarda cookies ────────────────────────────


def test_admin_proxy_forwards_support_mode_cookie_to_core():
    """Sin esto, el browser puede tener `copilotoia_support_mode` pero el
    proxy lo strippea al hablar con el Core → `authenticate_request` no
    lo lee → el toggle no aplica aunque la activación haya sido exitosa.
    """
    src = ADMIN_ROUTES.read_text()
    # La constante allowlist debe incluir el cookie de support_mode.
    assert "_CORE_API_FORWARDED_COOKIES = ('copilotoia_support_mode',)" in src or (
        '_CORE_API_FORWARDED_COOKIES' in src and "'copilotoia_support_mode'" in src
    )
    # El header `cookie` se construye desde el allowlist (no se reusa el
    # raw `request.headers['cookie']` — eso filtraría cookies de otros
    # dominios y el admin_session que es opaco al Core).
    assert 'request.cookies.get(name)' in src
    assert "headers['cookie']" in src


def test_admin_proxy_forwards_set_cookie_back_to_browser():
    """`set_cookie` del Core debe llegar al browser. Antes el proxy solo
    forwardeaba `content-type`, dejando el cookie HTTP-only del endpoint
    `POST /v1/me/support-mode/{tenant_id}` huérfano. Una sola response
    puede tener múltiples `Set-Cookie` (raros en este endpoint pero
    posible) — `.get_list('set-cookie')` los captura todos.
    """
    src = ADMIN_ROUTES.read_text()
    assert "upstream_response.headers.get_list('set-cookie')" in src
    # Append (no asignación) para multi-value support de Starlette
    # MutableHeaders. Asignación colapsaría a uno solo.
    assert "proxied.headers.append('set-cookie', set_cookie)" in src


def test_admin_proxy_does_not_forward_admin_session_cookie_to_core():
    """Defensive — el cookie `copilotoia_admin_session` es opaco al Core
    (es state de la sesión del BFF). Reenviarlo daría info sin uso al
    cluster productivo Y podría confundir su parser de cookies. El
    allowlist explícito sirve de gate.
    """
    src = ADMIN_ROUTES.read_text()
    # Encuentra el bloque de la constante allowlist.
    pattern = re.compile(r'_CORE_API_FORWARDED_COOKIES\s*=\s*\(([^)]*)\)', re.DOTALL)
    match = pattern.search(src)
    assert match, 'no encontré la constante _CORE_API_FORWARDED_COOKIES'
    allowlist = match.group(1)
    assert 'copilotoia_admin_session' not in allowlist, (
        'el admin_session NO debe forwardearse al Core — es opaco al cluster'
    )
    assert 'copilotoia_admin_oauth_state' not in allowlist


# ───── codex P1: usePermissions lee override del context si no se pasa ──


def test_use_permissions_reads_override_from_context_when_not_passed():
    """Sin este fix, TODOS los callers de `usePermissions` tendrían que
    pasar `supportModeOverride` explícito o el platform_owner que activó
    el toggle ve "Sin acceso a ningún módulo" en cualquier vista que
    olvidó pasarlo. La lectura del context es opt-in (returns null fuera
    del provider, así que tests aislados siguen funcionando).
    """
    use_perms = Path('admin-panel/src/permissions/usePermissions.js').read_text()
    # Import del context tolerante.
    assert 'useOptionalTenantContext' in use_perms
    # Default `undefined` (no `null`) para distinguir "no se pasó" vs
    # "se pasó explícitamente como null" — el primero hace fallback al
    # context, el segundo NO (caller pidió desactivar el override).
    assert 'supportModeOverride } = {}' in use_perms
    # Fallback al context cuando undefined.
    assert (
        'supportModeOverride === undefined ? (ctx?.supportModeOverride ?? null) : supportModeOverride'
    ) in use_perms


def test_use_permissions_passes_effective_override_to_resolve_active_roles():
    """El `effectiveOverride` (mezcla de prop + context) debe propagarse
    a `resolveActiveRoles`. Sin esto, el hook calcularía `isSystemOwner`
    con el override pero los `roles` con `null` — UI inconsistente.
    """
    use_perms = Path('admin-panel/src/permissions/usePermissions.js').read_text()
    assert (
        'resolveActiveRoles({ profile, tenant, supportModeOverride: effectiveOverride })'
    ) in use_perms
