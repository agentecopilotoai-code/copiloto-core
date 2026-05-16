"""Static tests para el bootstrap del platform_owner en `configure-auth0.sh`.

El script gestiona toda la configuración de Auth0 (API, apps, roles, Actions).
Hasta ahora, asignar el rol `platform_owner` al primer user + setear
`app_metadata.support_mode=true` quedaba como pasos manuales en Auth0
dashboard — fuente común de bugs operacionales (BUG-006, BUG-008).

Este test asegura que el bloque opt-in `BOOTSTRAP_PLATFORM_OWNER_EMAIL`
existe y:
  1. Es opt-in (no se ejecuta si la variable no está seteada).
  2. Falla loudly si el user no existe (no crea users a ciegas).
  3. Asigna el rol `platform_owner` vía Management API.
  4. Es idempotente (no duplica asignaciones de rol).
  5. Setea `app_metadata.support_mode` solo cuando el toggle correspondiente
     no es `false`.
  6. El script header documenta las dos variables nuevas.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

SCRIPT = Path('scripts/configure-auth0.sh')


def _script() -> str:
    return SCRIPT.read_text(encoding='utf-8')


# ───── Sanity ──────────────────────────────────────────────────────────────


def test_script_passes_bash_syntax_check():
    """Defensa básica: cualquier cambio al script no rompe la sintaxis bash."""
    result = subprocess.run(
        ['bash', '-n', str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f'bash -n falló:\nstdout={result.stdout}\nstderr={result.stderr}'
    )


# ───── Header documenta las variables nuevas ──────────────────────────────


def test_header_documents_bootstrap_email_variable():
    """El header del script tiene la convención de listar variables opcionales.
    Ambas nuevas deben aparecer ahí — sino los operadores nunca las descubren.
    """
    src = _script()
    # Buscamos en las primeras 80 líneas (header de doc comments).
    header = '\n'.join(src.splitlines()[:80])
    assert 'BOOTSTRAP_PLATFORM_OWNER_EMAIL' in header, (
        'el header del script debe listar BOOTSTRAP_PLATFORM_OWNER_EMAIL '
        'como variable opcional'
    )
    assert 'BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE' in header, (
        'el header debe listar la variable del toggle de support_mode'
    )


# ───── Bootstrap block — opt-in via env var ───────────────────────────────


def test_bootstrap_block_is_opt_in():
    """Sin BOOTSTRAP_PLATFORM_OWNER_EMAIL, el bloque NO debe ejecutarse —
    el operador sigue pudiendo correr el script "vainilla" sin trigger
    inesperado.
    """
    src = _script()
    # Default vacío.
    assert 'BOOTSTRAP_PLATFORM_OWNER_EMAIL="${BOOTSTRAP_PLATFORM_OWNER_EMAIL:-}"' in src
    # Guard explícito antes del bloque.
    assert 'if [ -n "$BOOTSTRAP_PLATFORM_OWNER_EMAIL" ]; then' in src


def test_bootstrap_support_mode_defaults_to_true():
    """Default es true — sin esto el botón 'Ver como tenant' del Platform
    Owner falla con 'Sin acceso a ningún módulo'. Es la causa más común
    de operadores trabados.
    """
    src = _script()
    assert (
        'BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE="${BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE:-true}"'
    ) in src


# ───── Bootstrap looks up user by email via Management API ────────────────


def test_bootstrap_searches_user_by_email_via_management_api():
    """Search by email es el endpoint `/users-by-email`. El email se URL-encodea
    con jq para que emails con caracteres especiales no rompan la query string.
    """
    src = _script()
    assert 'bootstrap_email_encoded' in src
    assert '$e | @uri' in src, (
        'el email debe URL-encodear con jq antes de mandarlo a Auth0'
    )
    assert 'api_get "/users-by-email?email=$bootstrap_email_encoded"' in src


def test_bootstrap_fails_loudly_if_user_does_not_exist():
    """Si el email no matchea ningún user, el script NO debe crear uno
    silenciosamente (los users en Auth0 requieren consent del dueño del
    email — Auth0 manda email de invitación). Debe fail-closed con
    instrucciones para el operador.
    """
    src = _script()
    # Detect del caso vacío via count (después del codex P1 fix migramos
    # de `-z $bootstrap_user_id` a counting con jq para soportar también
    # el caso de duplicados).
    assert 'bootstrap_user_count' in src
    assert 'if [ "$bootstrap_user_count" -eq 0 ]; then' in src
    # Mensaje útil para el operador.
    assert 'NO existe en Auth0' in src
    assert 'Crealo primero en Auth0 Dashboard' in src
    assert 'exit 2' in src


# ───── codex P1 #1: ambiguous email lookup ────────────────────────────────


def test_bootstrap_fails_if_email_matches_multiple_users():
    """codex P1: en Auth0 un mismo email puede existir en múltiples
    connections (database user + Google OAuth + Microsoft, etc.).
    `/users-by-email` devuelve TODOS los matches. Si silenciosamente
    tomáramos `.[0]`, asignaríamos privilegios a la identidad equivocada.

    El fix: contar matches y fail si != 1. El operador desambigua
    manualmente (borrando duplicates o asignando vía dashboard).
    """
    src = _script()
    # El guard del caso ambiguo.
    assert 'if [ "$bootstrap_user_count" -gt 1 ]; then' in src
    # Mensaje accionable que explica el problema y las acciones posibles.
    assert 'MÁS DE UN user en Auth0' in src
    assert 'múltiples connections' in src
    assert 'Acciones posibles:' in src
    # Lista los user_ids encontrados (con su connection) para que el
    # operador sepa exactamente qué desambiguar.
    assert 'jq -r \'.[]' in src
    assert '.identities[0].connection' in src
    # Fail-closed.
    src_lines = src.splitlines()
    ambiguous_block_started = False
    found_exit = False
    for line in src_lines:
        if 'if [ "$bootstrap_user_count" -gt 1 ]; then' in line:
            ambiguous_block_started = True
            continue
        if ambiguous_block_started:
            if 'exit 2' in line:
                found_exit = True
                break
            if line.strip() == 'fi':
                break
    assert found_exit, (
        'el branch de >1 user debe `exit 2` antes de cerrar el if — '
        'sin esto, el script seguiría con `.[0].user_id` aunque sea ambiguo'
    )


def test_bootstrap_user_id_extracted_only_after_ambiguity_guard():
    """`.[0].user_id` solo debe leerse DESPUÉS de validar que `length == 1`.
    Si está antes (o como fallback), reabrimos el oracle.
    """
    src = _script()
    # Localizar las posiciones relativas.
    count_pos = src.find('bootstrap_user_count="$(jq')
    ambiguous_guard_pos = src.find('-gt 1 ]; then')
    user_id_extract_pos = src.find("bootstrap_user_id=\"$(jq -r '.[0].user_id'")

    assert count_pos > 0 and ambiguous_guard_pos > 0 and user_id_extract_pos > 0
    assert count_pos < ambiguous_guard_pos < user_id_extract_pos, (
        'orden requerido: contar matches → guard `gt 1` con exit → recién '
        f'ahí extraer `.[0].user_id`. Posiciones: count={count_pos}, '
        f'guard={ambiguous_guard_pos}, extract={user_id_extract_pos}'
    )


# ───── codex P1 #2: URL-encode user_id for path segments ──────────────────


def test_bootstrap_url_encodes_user_id_for_path_segments():
    """codex P1: Auth0 user_ids tienen prefijo de connection separado por
    pipe (`auth0|abc123`, `google-oauth2|123`). El pipe `|` no es URL-safe
    y debe encodearse a `%7C` cuando va en path segments. Sin esto, los
    endpoints `/users/{id}/...` pueden fallar con 404/400 en algunos
    backends/proxies.
    """
    src = _script()
    # El helper de encoding existe.
    assert 'bootstrap_user_id_encoded' in src
    assert (
        "bootstrap_user_id_encoded=\"$(jq -rn --arg id \"$bootstrap_user_id\" '$id | @uri'"
    ) in src


def test_bootstrap_uses_encoded_id_in_all_user_endpoints():
    """Los TRES path segments deben usar la versión encoded:
      - GET /users/{id}/roles      (lectura de roles)
      - POST /users/{id}/roles     (asignación)
      - PATCH /users/{id}          (app_metadata)
    Si alguno se quedó con `$bootstrap_user_id` raw, reabre el bug.
    """
    src = _script()
    # Las 3 llamadas usan la versión encoded.
    assert 'api_get "/users/$bootstrap_user_id_encoded/roles?per_page=100"' in src
    assert 'api_post "/users/$bootstrap_user_id_encoded/roles" "$bootstrap_role_payload"' in src
    assert 'api_patch "/users/$bootstrap_user_id_encoded" "$bootstrap_user_payload"' in src

    # Y ninguna llamada usa el id raw (que es el bug original).
    # Permitimos `$bootstrap_user_id` para el extract inicial (no es path
    # segment) pero NO en endpoints `/users/...`.
    forbidden_patterns = (
        '/users/$bootstrap_user_id/',  # GET /users/{id}/...
        '/users/$bootstrap_user_id"',  # PATCH /users/{id}
    )
    for pattern in forbidden_patterns:
        assert pattern not in src, (
            f'path raw `{pattern}` reabre el bug — debe ser '
            'bootstrap_user_id_encoded'
        )


# ───── Bootstrap assigns platform_owner role ──────────────────────────────


def test_bootstrap_finds_platform_owner_role_id_from_roles_json():
    """El bloque reusa la variable `roles_json` que ya carga el script al
    crear roles. Si esa variable se renombra, el bootstrap deja de
    encontrar el rol y falla — el test fija el contrato.
    """
    src = _script()
    assert (
        "bootstrap_platform_role_id=\"$(jq -r '.[] | select(.name == \"platform_owner\") | .id' <<<\"$roles_json\""
    ) in src


def test_bootstrap_assignment_is_idempotent():
    """Si el rol ya está asignado, el script NO debe re-asignarlo (sería
    no-op para Auth0 pero generaría ruido en audit logs). Verificamos
    contra el listado actual antes del POST.

    Después del codex P1 fix de URL-encoding, los paths usan
    `$bootstrap_user_id_encoded` en vez del id raw.
    """
    src = _script()
    # Pre-check de roles ya asignados.
    assert 'api_get "/users/$bootstrap_user_id_encoded/roles?per_page=100"' in src
    assert 'bootstrap_already_assigned' in src
    # Mensaje "ya estaba asignado" cuando se skipea.
    assert 'idempotente' in src


def test_bootstrap_assigns_role_via_management_api_post():
    """POST /users/{id}/roles con payload {roles:[role_id]}.

    Después del codex P1 fix de URL-encoding, el id en el path va
    encodeado (auth0|abc → auth0%7Cabc).
    """
    src = _script()
    assert 'api_post "/users/$bootstrap_user_id_encoded/roles" "$bootstrap_role_payload"' in src
    # Payload usa el role_id resuelto.
    assert (
        'bootstrap_role_payload="$(jq -n --arg rid "$bootstrap_platform_role_id"'
    ) in src


# ───── Bootstrap sets app_metadata.support_mode under the toggle ──────────


def test_bootstrap_sets_support_mode_when_toggle_is_true():
    """Cuando BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE=true (default), se
    setea `app_metadata.support_mode=true` vía PATCH /users/{id}.

    Después del codex P1 fix de URL-encoding, el id en el path va
    encodeado.
    """
    src = _script()
    assert 'if [ "$BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE" = "true" ]; then' in src
    # Payload correcto — app_metadata es el namespace, NO user_metadata.
    assert (
        "bootstrap_user_payload=\"$(jq -n '{app_metadata:{support_mode:true}}'"
    ) in src
    assert 'api_patch "/users/$bootstrap_user_id_encoded" "$bootstrap_user_payload"' in src


def test_bootstrap_warns_about_support_mode_security_tradeoff():
    """Documentar el trade-off en stdout — el operador lee el output del
    script y debe enterarse que support_mode permanente es un compromiso.
    """
    src = _script()
    assert 'Trade-off' in src or 'trade-off' in src
    # Referencia al BUG-008 que cierra el follow-up correcto (toggle endpoint).
    assert 'BUG-008' in src


def test_bootstrap_skip_path_warns_about_view_as_tenant():
    """Cuando el toggle es false, el script avisa al operador que el
    botón "Ver como tenant" del panel va a fallar. Sin este warning,
    el operador queda confundido cuando lo intente.
    """
    src = _script()
    # En el branch else (NO seteado).
    assert "Ver como tenant" in src
    assert 'rechazará acceso' in src or 'rechaza acceso' in src


# ───── Header opt-in flag documentado coherentemente ──────────────────────


def test_bootstrap_block_referenced_in_header_section():
    """Las variables opcionales en el header deben describir el efecto
    completo — sin ese contexto, el operador no sabe que el user debe
    existir previamente.
    """
    src = _script()
    header = '\n'.join(src.splitlines()[:80])
    # El caveat "el user debe existir previamente en Auth0" puede estar
    # partido entre dos líneas de comentario (`# ... debe\n#  existir ...`).
    # Normalizamos antes de matchear: collapse de `\s+#\s+` (continuación
    # de comentario) en un solo espacio.
    flat_header = re.sub(r'\s*#\s+', ' ', header)
    assert re.search(
        r'user\s+debe\s+existir', flat_header, re.IGNORECASE
    ), 'el header del script debe documentar que el user debe existir previamente en Auth0'


# ───── BUG-001 follow-up: Management API client grant ─────────────────────


def test_script_creates_client_grant_for_auth0_management_api():
    """BUG-001 follow-up: el script crea la app M2M pero antes NO le
    autorizaba Auth0 Management API. Resultado: invite member respondía
    403 en /oauth/token aún con el setup "correcto". Ahora el script
    crea/upsertea el grant automáticamente.
    """
    src = _script()
    # Constantes a nivel script.
    assert 'MGMT_API_AUDIENCE="https://${AUTH0_DOMAIN}/api/v2/"' in src
    assert 'MGMT_API_SCOPES=' in src
    # Bloque de upsert del grant.
    assert "▶ Upsert client grant M2M hacia Management API" in src
    # Idempotente: detecta si ya existe y hace PATCH; si no, POST.
    assert 'mgmt_grant_id' in src
    assert "api_post '/client-grants' \"$mgmt_grant_payload\"" in src
    assert 'api_patch "/client-grants/$mgmt_grant_id"' in src


def test_management_api_scopes_include_all_runtime_dependencies():
    """Los scopes deben cubrir TODAS las operaciones que el backend hace
    runtime contra Management API. Si alguien quita uno, los endpoints
    correspondientes (invite, role assignment, etc.) van a fallar 403.

    Lista mínima derivada de:
      - app/services/auth0_admin.py::invite_user (create:users +
        create:user_tickets para POST /api/v2/tickets/password-change)
      - app/services/auth0_admin.py::assign_roles (create:role_members + read:roles)
      - Look-ups de roles para resolver el role_id (read:roles, read:role_members)
      - Update de app_metadata post-invite (BUG-009 fix futuro: update:users)

    codex P1 fix: el scope para crear tickets es `create:user_tickets`
    (no `read:tickets` — ese es para lectura de tickets existentes y NO
    autoriza la creación). Confundirlos hace que Auth0 emita un token
    sin el scope correcto y el invite siga fallando.
    """
    src = _script()
    # Extraer la línea MGMT_API_SCOPES=...
    match = re.search(r'MGMT_API_SCOPES="([^"]+)"', src)
    assert match, 'no encontré MGMT_API_SCOPES= en el script'
    scopes = set(match.group(1).split(','))
    required_scopes = {
        'read:users',
        'create:users',
        'update:users',
        'create:user_tickets',
        'read:roles',
        'read:role_members',
        'create:role_members',
    }
    missing = required_scopes - scopes
    assert not missing, (
        f'MGMT_API_SCOPES no incluye scopes requeridos: {missing}. '
        'Si los quitás, endpoints como /v1/tenants/{id}/members fallarán 403.'
    )
    # codex P1 regression gate: `read:tickets` NO debe aparecer porque NO
    # autoriza la creación del password-change ticket (endpoint POST
    # /api/v2/tickets/password-change exige create:user_tickets).
    assert 'read:tickets' not in scopes, (
        '`read:tickets` no es el scope correcto para crear tickets — '
        'usar `create:user_tickets`. Ver codex review en PR #218.'
    )


def test_management_api_audience_uses_auth0_domain_var():
    """El audience debe construirse desde `AUTH0_DOMAIN` (env var del
    operador) y NO ser un literal. Sin esto el script solo funcionaría
    contra un tenant Auth0 específico.
    """
    src = _script()
    assert 'MGMT_API_AUDIENCE="https://${AUTH0_DOMAIN}/api/v2/"' in src
    # El audience pasado al grant payload usa la variable, no un literal.
    assert '--arg audience "$MGMT_API_AUDIENCE"' in src
