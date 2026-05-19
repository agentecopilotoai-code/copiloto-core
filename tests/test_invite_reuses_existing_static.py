"""BUG-013 — defienden el patrón "reuse existing Auth0 user" en invite_user.

Caso de uso: SaaS multi-tenant. Un agente o consultor trabaja para varias
empresas. El primer invite (tenant A) crea cuenta Auth0. Los siguientes
invites (tenant B, C, ...) deben:
  1. Detectar el 409 del POST /api/v2/users.
  2. Hacer lookup por email vía GET /api/v2/users-by-email.
  3. Reutilizar el user_id existente.
  4. NO emitir password-change ticket (el user ya tiene credenciales).
  5. Retornar {'reused_existing': True} para que el frontend muestre
     "Agregado al equipo" (no "Invitación enviada").

Antes del fix: el segundo invite fallaba con 409 → frontend mostraba
error → el caso de uso central del SaaS multi-tenant estaba roto.

Si alguien revierte el fix (vuelve a propagar Auth0UserAlreadyExists sin
intentar lookup), este suite falla loudly.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import auth0_admin
from tests._routes_aggregator import routes_aggregated_source

AUTH0 = Path('app/services/auth0_admin.py')
USE_TEAM_DATA = Path('admin-panel/src/features/owner-admin/team/hooks/useTeamData.js')


def _handler_source(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(auth0_admin, name)))


# ───── lookup helper existe + tiene la forma esperada ─────────────────────


def test_lookup_helper_exists():
    """El helper compartido `lookup_auth0_user_by_email` debe estar exportado
    desde `auth0_admin` para que sea reutilizable (tests, otros flows)."""
    assert hasattr(auth0_admin, 'lookup_auth0_user_by_email')
    sig = inspect.signature(auth0_admin.lookup_auth0_user_by_email)
    assert 'email' in sig.parameters


def test_lookup_helper_uses_users_by_email_endpoint():
    """El endpoint correcto es `/users-by-email` (NO `/users?email=...`,
    que es deprecated en Auth0)."""
    src = _handler_source('lookup_auth0_user_by_email')
    assert '/users-by-email' in src


def test_lookup_helper_url_encodes_email():
    """Emails con caracteres reservados (`+`, `%`, etc.) deben URL-encodearse
    sino el GET falla o devuelve resultados incorrectos."""
    src = _handler_source('lookup_auth0_user_by_email')
    assert 'urllib' in src or 'quote' in src
    assert 'quote(email)' in src or 'quote_plus(email)' in src


def test_lookup_helper_respects_auth0_management_enabled():
    """En dev local sin credenciales Auth0, el helper debe devolver None
    silencioso (no crashear)."""
    src = _handler_source('lookup_auth0_user_by_email')
    assert 'auth0_management_enabled()' in src


def test_lookup_helper_returns_first_match_or_none():
    """El endpoint Auth0 retorna un array. Si está vacío → None. Si hay 1
    match válido (single + email_verified) lo retornamos.

    BUG-193 (fix-group-35): el patrón anterior `return response[0]` blindly
    se reemplazó por una validación que (a) levanta `Auth0AmbiguousUserMatch`
    si `enforce_single` y hay >1 match, y (b) levanta `Auth0UserNotVerified`
    si `require_email_verified` y el match no tiene `email_verified=true`.
    El "return del candidato" sigue presente — solo está gateado por los
    chequeos de seguridad.
    """
    src = _handler_source('lookup_auth0_user_by_email')
    # El path "lista vacía → None" sigue presente.
    assert 'return None' in src
    # El "return del candidato validado" sigue siendo terminal en el happy path.
    assert 'return candidate' in src or 'return response[0]' in src


# ───── invite_user integra el lookup en el catch del 409 ──────────────────


def test_invite_user_catches_already_exists_and_does_lookup():
    """Patrón central del fix: el `except Auth0UserAlreadyExists` debe
    llamar `lookup_auth0_user_by_email` para recuperar el user_id existente.
    """
    src = _handler_source('invite_user')
    assert 'except Auth0UserAlreadyExists:' in src
    # El except debe invocar el lookup ANTES de re-raisear.
    except_block = src[src.index('except Auth0UserAlreadyExists:'):]
    # Quedarse con el bloque del except (hasta el siguiente except o fin del try).
    except_block_end = except_block.find('\n    except ')
    if except_block_end > 0:
        except_block = except_block[:except_block_end]
    assert 'lookup_auth0_user_by_email' in except_block, (
        'El catch del 409 debe invocar lookup_auth0_user_by_email para reusar '
        'el user existente. Sin esto, el caso SaaS multi-tenant se rompe.'
    )


def test_invite_user_only_raises_when_lookup_returns_nothing():
    """El except debe re-raisear SOLO cuando el lookup también falla
    (devuelve None o user sin user_id). En el happy path el lookup encuentra
    el user y NO se raisea — el invite continúa."""
    src = _handler_source('invite_user')
    except_block = src[src.index('except Auth0UserAlreadyExists:'):]
    # Después del lookup, hay un `if not existing` (o equivalent) que `raise`.
    assert 'raise' in except_block
    # Y existing.get('user_id') o similar — defensivo.
    assert "'user_id'" in except_block or '.get(' in except_block


def test_invite_user_sets_reused_existing_flag_in_response():
    """El response final debe incluir `reused_existing` para que el caller
    pueda distinguir "user creado de cero" vs "user pre-existente reutilizado"
    y mostrar UX apropiada (skip welcome email message)."""
    src = _handler_source('invite_user')
    assert "'reused_existing': reused_existing" in src
    # La variable se inicializa antes del try (False) y se setea a True solo
    # en el path del lookup exitoso.
    assert 'reused_existing = False' in src
    assert 'reused_existing = True' in src


def test_invite_user_skips_password_ticket_when_reused():
    """Cuando reused_existing=True, el ticket de password-change NO se emite.
    Mandar un reset-password mail a un user existente sería: (a) UX confuso,
    (b) bordeline-malicious (phishing-via-legitimate-channel)."""
    src = _handler_source('invite_user')
    # El bloque del ticket debe estar dentro de un `if not reused_existing:`
    # (o equivalent guard).
    assert 'if not reused_existing:' in src
    # Y dentro de ese guard, está el POST /tickets/password-change.
    guard_pos = src.find('if not reused_existing:')
    ticket_pos = src.find("'/tickets/password-change'")
    assert guard_pos > 0 and ticket_pos > guard_pos, (
        'El POST /tickets/password-change debe estar gated por `not reused_existing` '
        '— sino mandamos email de reset a users que no lo pidieron.'
    )


def test_invite_user_logs_reused_event_for_observability():
    """Cuando se reusa un user existente, el log debe registrarlo
    explícitamente — el operador necesita poder distinguir invites nuevos
    de reutilizaciones en los logs."""
    src = _handler_source('invite_user')
    assert "'auth0_admin.invite_user_reused_existing'" in src


# ───── Routes: response incluye reused_existing ──────────────────────────


def test_routes_propagate_reused_existing_to_safe_auth0_response():
    """El handler de routes debe incluir `reused_existing` en el `safe_auth0`
    que se devuelve al frontend, sino la UX no puede distinguir los casos."""
    routes_src = routes_aggregated_source()
    # safe_auth0 dict literal incluye la key.
    assert "'reused_existing': bool(auth0_result.get('reused_existing'))" in routes_src


# ───── Frontend: usa el flag para mensaje distinto ───────────────────────


def test_frontend_shows_distinct_message_when_user_reused():
    """El hook `useTeamData` debe chequear `result?.auth0?.reused_existing`
    antes del check genérico `result?.auth0?.invited` (que ahora también es
    true para reused). Sin esto, el admin recibe el mensaje "invitación
    enviada" y espera un email que nunca llega."""
    src = USE_TEAM_DATA.read_text()
    assert 'result?.auth0?.reused_existing' in src
    # Mensaje distinto al de invitación nueva.
    # El test no fija las palabras exactas (puede traducirse), pero verifica
    # que hay al menos DOS mensajes de éxito distintos en la rama del invite
    # (uno para reused, uno para invited fresh).
    reused_pos = src.find('reused_existing')
    invited_pos = src.find("'success'", reused_pos)
    fresh_invited_pos = src.find("result?.auth0?.invited", reused_pos)
    assert invited_pos > 0 and fresh_invited_pos > 0, (
        'useTeamData debe tener mensaje distinto para reused vs fresh invite.'
    )
