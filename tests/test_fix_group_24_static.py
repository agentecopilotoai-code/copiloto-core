"""Fix-group 24: BUG-138..BUG-142 — all NOT-APPLICABLE (regression defense).

Los 5 bugs fueron señalados en review-bot de PRs vmantilla/CopilotoIA y
posteriormente arreglados en commits follow-up que NO marcaron los hilos
de review. Este test cubre el statu-quo defensivamente: si alguien re-
introduce el anti-patrón, el grupo correspondiente vuelve a aplicar.

- BUG-138: `_build_widget_snippet` debe emitir data-logo / data-welcome
  / data-position cuando llegan en el payload. Hoy lo hace correctamente
  (líneas 3587-3593 de routes.py).
- BUG-139: `_verify_onboarding_business_hours` filtra `if ranges:`
  (rechaza días vacíos) y retorna False si `not populated`. Hoy lo hace.
- BUG-140: `_verify_onboarding_end_to_end_test` cierra el query con
  `c.wa_id=$3` (target_wa_id del admin), no acepta cualquier inbound
  post-timestamp.
- BUG-141: `app.users.id` es `uuid primary key default gen_random_uuid()`
  y `auth_subject` es `text` separado. La INSERT en `current_user_id_from_request`
  pasa el sub Auth0 a la columna `auth_subject` (no a `id`).
- BUG-142: `app.messages.sender_actor_id` es `text` (no UUID), así que
  nunca se cast a UUID en Python — el string del actor (auth0|abc) o el
  UUID stringificado caben igual.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


SCHEMA = Path('infra/postgres/01-schema.sql')


# ───── BUG-138 — widget snippet incluye los 6 campos ─────────────────────


def test_bug_138_widget_snippet_emits_logo_welcome_position():
    src = routes_aggregated_source()
    snip_idx = src.find('def _build_widget_snippet(')
    assert snip_idx > 0
    next_def = src.find('\n\n\n', snip_idx)
    block = src[snip_idx:next_def]
    # Los 3 campos extra (logo, welcome, position) deben aparecer como
    # data-* attributes en el snippet generado.
    # BUG-138 original: el snippet emite `data-logo="…"`.
    # BUG-226 (fix-group-43, 2026-05-18): el valor se HTML-escapea (`"`→`&quot;`,
    # `<`/`>` también) antes de la interpolación para prevenir XSS via
    # `logo_url=x" onload=...`. La variable usada en la f-string es
    # `safe_logo`, no `logo_url` raw.
    assert "f'data-logo=\"{safe_logo}\"'" in block, (
        'BUG-138 + BUG-226: el snippet debe emitir `data-logo="{safe_logo}"` '
        'donde `safe_logo` es el `logo_url` con `"`/`<`/`>` HTML-escapados.'
    )
    assert "f'data-welcome=\"{safe}\"'" in block, (
        'BUG-138: el snippet debe emitir `data-welcome="…"` cuando llega `welcome_copy`.'
    )
    assert "f'data-position=\"{button_position}\"'" in block, (
        'BUG-138: el snippet debe emitir `data-position="…"` cuando llega `button_position`.'
    )


def test_bug_138_put_channels_web_passes_all_three_fields():
    src = routes_aggregated_source()
    put_idx = src.find("@tenant_admin_router.put('/tenants/{tenant_id}/channels/web')")
    assert put_idx > 0
    next_route = src.find('\n@', put_idx + 10)
    block = src[put_idx:next_route]
    assert 'logo_url=widget_config.get(' in block
    assert 'welcome_copy=widget_config.get(' in block
    assert 'button_position=widget_config.get(' in block, (
        'BUG-138: el PUT /channels/web debe pasar los 6 campos al snippet '
        '(`logo_url`, `welcome_copy`, `button_position` además de los 3 base).'
    )


# ───── BUG-139 — verifier rechaza días vacíos ────────────────────────────


def test_bug_139_business_hours_verifier_rejects_all_empty_days():
    src = routes_aggregated_source()
    ver_idx = src.find('async def _verify_onboarding_business_hours(')
    assert ver_idx > 0
    next_def = src.find('\n\nasync def ', ver_idx)
    block = src[ver_idx:next_def]
    # El filtro `if ranges:` excluye días con [] / None / ''.
    assert 'if ranges' in block, (
        'BUG-139: el verifier debe filtrar `if ranges:` para no contar '
        'días sin rangos como "configurados".'
    )
    # Y debe retornar False si `not populated`.
    assert 'if not populated' in block and "'Ningún día tiene rangos de atención definidos.'" in block, (
        'BUG-139: si todos los días están vacíos, el verifier debe '
        'retornar False con mensaje claro.'
    )


# ───── BUG-140 — E2E verifier filtra por target_wa_id ────────────────────


def test_bug_140_e2e_verifier_filters_by_target_wa_id():
    src = routes_aggregated_source()
    ver_idx = src.find('async def _verify_onboarding_end_to_end_test(')
    assert ver_idx > 0
    next_def = src.find('\n\n\nONBOARDING_VERIFIERS', ver_idx)
    block = src[ver_idx:next_def]
    # El SQL debe filtrar por c.wa_id=$3 — sino, cualquier inbound de
    # cualquier contacto post-timestamp lo cuenta como E2E exitoso.
    assert 'c.wa_id=$3' in block, (
        'BUG-140: el E2E verifier debe filtrar el inbound por '
        '`c.wa_id=$3` (target_wa_id del admin). Sin esto, otro cliente '
        'puede completar el onboarding por accidente.'
    )
    # El 3er parámetro pasado al fetchrow debe ser str(target_wa_id).
    assert 'str(target_wa_id)' in block, (
        'BUG-140: el verifier debe pasar `str(target_wa_id)` como 3er param.'
    )


# ───── BUG-141 — users.id es UUID, auth_subject es text ──────────────────


def test_bug_141_users_schema_separates_id_from_auth_subject():
    src = SCHEMA.read_text()
    create_idx = src.find('create table app.users (')
    assert create_idx > 0
    end = src.find(');', create_idx)
    block = src[create_idx:end]
    assert 'id uuid primary key default gen_random_uuid()' in block, (
        'BUG-141: `users.id` debe ser uuid auto-generado, separado de auth_subject.'
    )
    assert 'auth_subject text not null unique' in block, (
        'BUG-141: `users.auth_subject` debe ser text (acepta `auth0|abc`, '
        '`pending|<hash>`, etc.). Si fuera uuid, los subs no-UUID romperían.'
    )


def test_bug_141_current_user_id_inserts_actor_into_auth_subject_column():
    src = routes_aggregated_source()
    fn_idx = src.find('async def current_user_id_from_request(')
    assert fn_idx > 0
    next_def = src.find('\n\n@', fn_idx)
    block = src[fn_idx:next_def]
    # Confirmamos que el INSERT escribe `auth_subject` (no `id`):
    assert 'insert into app.users (auth_subject, email, display_name, last_login_at)' in block, (
        'BUG-141: el INSERT debe escribir el actor_id en la columna '
        '`auth_subject`, no en `id` (que es auto-UUID).'
    )
    assert 'returning id' in block, (
        'BUG-141: el INSERT debe `returning id` (UUID auto-generado), no `auth_subject`.'
    )


# ───── BUG-142 — sender_actor_id es text en schema ───────────────────────


def test_bug_142_messages_sender_actor_id_is_text_not_uuid():
    src = SCHEMA.read_text()
    msg_idx = src.find('create table app.messages (')
    assert msg_idx > 0
    end = src.find(');', msg_idx)
    block = src[msg_idx:end]
    # Sender actor id text — acepta `auth0|abc`, `uuid-stringified`, etc.
    assert 'sender_actor_id text' in block, (
        'BUG-142: `messages.sender_actor_id` debe ser `text`, no `uuid` — '
        'el sub Auth0 (`auth0|abc`) y otros actor_ids no-UUID deben caber.'
    )


def test_bug_142_no_uuid_cast_on_sender_actor_id_in_routes():
    """Regresión: si alguien añade `UUID(sender_actor_id)` o
    `sender_actor_id::uuid`, romperá runs con auth subjects no-UUID.
    """
    src = routes_aggregated_source()
    assert 'UUID(sender_actor_id)' not in src, (
        'BUG-142: no convertir `sender_actor_id` a UUID — la columna es text '
        'y el valor puede ser `auth0|abc` (no parseable).'
    )
    assert 'sender_actor_id::uuid' not in src, (
        'BUG-142: no castear `sender_actor_id::uuid` en SQL — la columna ya '
        'es text. Si necesitas join con users.id (uuid), castear EL OTRO lado '
        '(`users.id::text`).'
    )
