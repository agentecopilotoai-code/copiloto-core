"""BUG-022: el invitado por `POST /v1/tenants/{id}/members` que después de
aceptar el email de Auth0 y autenticarse aterriza en `/admin/no-tenant`.

## Por qué pasaba

`invite_tenant_member` (routes.py ~2113) crea la fila en `app.users` con
`auth_subject = 'pending|<uuid5(email).hex>'` antes de hablar con Auth0 — el
schema obliga a que `auth_subject` sea NOT NULL UNIQUE, así que el handler
necesita un placeholder estable que no colisione con ningún `auth0|...` real.

La fila de membresía (`user_tenant_roles`) se crea contra esa fila placeholder,
así que el link tenant→user existe.

En el happy path, `auth0_invite_user` devuelve el `auth0_user_id` real y el
handler hace `UPDATE app.users SET auth_subject = 'auth0|...'`. Pero ese
UPDATE vive dentro del `else:` del try/except — si **cualquier** paso entre
la creación del user Auth0 y el final del invite lanza una excepción (típica
en errores transitorios de Management API: 429, 5xx, timeouts), entra al
`except`, no toca `auth_subject`, y la fila queda `pending|...` para siempre.

Cuando el invitado finalmente loguea:
- JWT `sub = 'auth0|<id>'`
- `GET /v1/me/tenants` filtra `where u.auth_subject = $1` con $1 = sub
- No matchea ninguna fila → array vacío → admin-panel envía a `/admin/no-tenant`

## Fix

`current_user_id_from_request` ahora primero intenta **reclamar** la fila
`pending|<hex>` matcheando el email del JWT con `app.users.email`. Si hay
match, hace UPDATE y le pega el `auth_subject` real (y marca `status='active'`).
Es idempotente: sólo afecta filas con `auth_subject LIKE 'pending|%'`, y un
`NOT EXISTS` defiende del UNIQUE en `auth_subject` por si ya hay otra fila
con ese `sub`.

`list_my_tenants` (`GET /v1/me/tenants`) ahora llama a
`current_user_id_from_request` **antes** de la query — este endpoint es
típicamente el primer hit del invitado al loguear (el admin-panel lo
invoca para decidir si mostrar el switcher o mandarlo a `/admin/no-tenant`),
así que el reclamo se dispara en el momento exacto en que se necesita.

Estos tests bloquean cualquier regresión que: (a) saque el branch de
reclamo de `current_user_id_from_request`, o (b) remueva la llamada desde
`list_my_tenants`.
"""
from __future__ import annotations

import inspect
import textwrap

from app.api.v1 import routes as routes_module


def _source_of(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(routes_module, name)))


# ───── current_user_id_from_request: reclamo de fila pendiente por email ─


def test_current_user_id_claims_pending_invite_row_by_email():
    """El helper debe intentar UPDATE sobre `app.users` matcheando por email
    y `auth_subject LIKE 'pending|%'` ANTES del upsert normal — sin esto el
    invitado se queda huérfano y `/me/tenants` devuelve vacío."""
    source = _source_of('current_user_id_from_request')
    # El reclamo es un UPDATE sobre app.users.
    assert 'update app.users' in source.lower(), (
        'BUG-022: current_user_id_from_request debe reclamar la fila pendiente '
        'haciendo UPDATE app.users — si esta sentencia desaparece, el invitado '
        'vuelve a aterrizar en /admin/no-tenant después de loguear.'
    )
    # El reclamo filtra por email y por el patrón placeholder 'pending|%'.
    assert "auth_subject like 'pending|%'" in source.lower(), (
        "BUG-022: el reclamo debe filtrar `auth_subject LIKE 'pending|%'` para "
        'tocar SÓLO filas placeholder generadas por invite_tenant_member.'
    )
    assert 'email = $2' in source.lower(), (
        'BUG-022: el reclamo debe matchear por email (el JWT trae email + sub; '
        'el sub es nuevo, el email es el puente al row pendiente).'
    )
    # El UPDATE setea el sub real y marca la fila activa.
    assert 'set auth_subject = $1' in source.lower(), (
        'BUG-022: el reclamo debe pegar el `auth_subject` real del JWT a la '
        'fila pendiente.'
    )
    assert "status = 'active'" in source.lower(), (
        "BUG-022: el reclamo debe transicionar status='invited' → 'active' al "
        'completar el flujo de invitación.'
    )
    # Defensa contra UNIQUE: si ya existe otra fila con ese sub, no toca nada.
    assert 'not exists' in source.lower(), (
        'BUG-022: el reclamo debe llevar guarda `NOT EXISTS` para no chocar '
        'con UNIQUE(auth_subject) cuando ya existe otra fila con ese sub.'
    )


def test_current_user_id_claim_runs_before_normal_upsert():
    """Orden importa: si el upsert corre primero, FALLA por UNIQUE(email) y
    nunca tocamos la fila pendiente. El reclamo va antes."""
    source = _source_of('current_user_id_from_request')
    claim_index = source.lower().find("auth_subject like 'pending|%'")
    upsert_index = source.lower().find('on conflict (auth_subject) do update')
    assert claim_index >= 0 and upsert_index >= 0, (
        'BUG-022: faltan tanto el reclamo pending como el upsert normal en '
        'current_user_id_from_request.'
    )
    assert claim_index < upsert_index, (
        'BUG-022: el reclamo de fila pendiente debe ejecutarse ANTES del '
        'upsert normal — sino el INSERT del upsert choca con UNIQUE(email) '
        'porque la fila pendiente ya tiene ese email.'
    )


def test_current_user_id_only_claims_when_trusted_jwt_email_present():
    """SEGURIDAD (Codex P1, PR #17): el reclamo SÓLO puede usar el claim
    `email` del JWT (`request.state.email`). Si usara el helper genérico
    `user_email_from_request`, fallback al header `X-Admin-User-Email` y
    al email sintético `<hash>@auth.local` — y un atacante autenticado
    con su propio sub podría mandar `X-Admin-User-Email: víctima@ejemplo.com`
    y reclamar la membresía pendiente para sí mismo.
    """
    source = _source_of('current_user_id_from_request')
    # El reclamo debe usar request.state.email (la única fuente confiable).
    assert 'trusted_email' in source or "request.state, 'email'" in source, (
        'BUG-022 / SEC: el reclamo debe leer email SÓLO del JWT '
        "(`request.state.email`), no del helper `user_email_from_request` que "
        'cae al header X-Admin-User-Email.'
    )
    # El reclamo no debe pasar por user_email_from_request (que cae al header).
    claim_block_start = source.lower().find("auth_subject like 'pending|%'")
    claim_block_context = source[max(0, claim_block_start - 500):claim_block_start + 200]
    assert 'user_email_from_request' not in claim_block_context, (
        'BUG-022 / SEC: el bloque de reclamo NO debe usar '
        '`user_email_from_request` (que cae a header X-Admin-User-Email no '
        'confiable). Usar `request.state.email` directamente.'
    )
    # La guarda debe existir.
    assert 'if trusted_email' in source or 'if user_email' in source, (
        'BUG-022: el reclamo debe estar gateado por `if <email>:` para no '
        'matchear contra strings vacíos o None cuando el JWT no trae email.'
    )


def test_normal_upsert_keeps_fallback_email_helper():
    """El INSERT del path normal SÍ puede usar `user_email_from_request`
    porque (a) el conflict es sobre `auth_subject`, no `email`, así que el
    header fallback no abre vector de claim, y (b) hace falta el email
    sintético para que el NOT NULL de la columna no rompa flujos legacy
    (tokens de servicio, callers sin email claim)."""
    source = _source_of('current_user_id_from_request')
    upsert_index = source.lower().find('on conflict (auth_subject) do update')
    assert upsert_index >= 0
    assert 'user_email_from_request' in source, (
        'El path de upsert normal aún necesita user_email_from_request para '
        'cubrir tokens sin email claim — pero el reclamo NO debe usarlo.'
    )


# ───── list_my_tenants: invoca el reclamo en el primer hit del invitado ──


def test_list_my_tenants_invokes_user_resolution_before_join():
    """`/me/tenants` es típicamente el primer hit autenticado del invitado.
    Debe llamar `current_user_id_from_request` antes de la query principal
    para que el reclamo corra justo a tiempo — sin esto, el primer load del
    admin-panel siempre mostraría /admin/no-tenant para invitados."""
    source = _source_of('list_my_tenants')
    assert 'current_user_id_from_request(request, conn)' in source, (
        'BUG-022: list_my_tenants debe invocar current_user_id_from_request '
        'antes del SELECT — es el momento exacto donde el reclamo se necesita.'
    )
    # La llamada debe ir ANTES del SELECT (orden importa).
    call_index = source.find('current_user_id_from_request(request, conn)')
    select_index = source.lower().find('from app.users u')
    assert call_index < select_index, (
        'BUG-022: la llamada a current_user_id_from_request debe ir ANTES del '
        'SELECT principal — si va después, el reclamo se ejecuta pero la query '
        'ya devolvió vacío.'
    )


# ───── Multi-tenant: un email puede ser invitado a varios negocios ───────


def test_invite_handler_reuses_existing_user_row_for_multi_tenant_invites():
    """Un mismo email puede tener invitaciones a varios tenants con roles
    diferentes (caso típico SaaS: un agente externo trabaja para varios
    negocios). `invite_tenant_member` debe reutilizar la fila `app.users`
    existente en lugar de crear una nueva — de lo contrario chocaría con
    UNIQUE(email) o crearía filas huérfanas.

    Cuando el reclamo de BUG-022 dispara, TODAS las memberships pendientes
    de ese user_id quedan accesibles a la vez (comparten `user_id`)."""
    source = _source_of('invite_tenant_member')
    # Lookup por email para reutilizar fila existente.
    assert "select id, auth_subject from app.users where email=$1" in source, (
        'Multi-tenant: invite_tenant_member debe hacer lookup por email para '
        'reutilizar la fila app.users existente cuando un mismo email es '
        'invitado a un segundo tenant.'
    )
    # Reuso explícito: usar user_id existente sin re-insert.
    assert 'if existing:' in source, (
        'Multi-tenant: invite_tenant_member debe tomar el branch `if existing:` '
        'cuando la fila ya existe, evitando re-insertar (UNIQUE(email) chocaría).'
    )
    # La membership SIEMPRE se crea (independiente de si la fila users es nueva).
    assert 'insert into app.user_tenant_roles' in source, (
        'Multi-tenant: invite_tenant_member debe insertar SIEMPRE en '
        'user_tenant_roles — esa es la fuente del binding tenant↔user↔role; '
        'reutilizar la fila users no implica saltar este insert.'
    )
