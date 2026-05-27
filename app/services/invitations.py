"""Generación y envío de invitaciones a miembros del tenant (M61).

Reemplaza la dependencia de "Auth0 manda email" — porque Auth0 NO manda
email automáticamente cuando creás un password-change ticket via
Management API. Hasta hoy: usuarios nuevos quedaban "pendientes" sin
notificación; usuarios existentes (`reused_existing` branch) ni siquiera
recibían un link.

Flow:

  1. `add_tenant_member` invoca `create_and_send_invitation(...)` con
     el email del invitado + tenant + role + actor.
  2. Generamos un token opaco (32 bytes hex, ~64 chars) + su hash sha256.
  3. INSERT en `app.tenant_invitations` (solo guardamos el hash; el
     token clear queda solo en el email enviado).
  4. Renderizamos template ES con `accept_url` = `{APP_PUBLIC_URL}/i/<token>`.
  5. Llamamos al provider (Resend prod, Noop dev) para mandar el email.
  6. UPDATE `tenant_invitations.last_send_*` con el message_id del provider.
  7. Devolvemos `{invitation_id, accept_url, message_id, status}` al handler.

Casos cubiertos:

  - User nuevo en Auth0: invitación crea token → email con link → user
    click → completa signup Auth0 → M57 reconcilia + (iteración 2) redime
    la invitación.
  - User existente en Auth0 (`reused_existing`): TAMBIÉN se crea
    invitación + se manda email — porque aunque puedan loguearse, sigue
    siendo cortés avisarles "te agregaron a TenantX". Antes esto era
    silencioso.
  - Re-invitar (mismo email, mismo tenant, invitación previa no
    redimida): el caller (iteración 2 via /invitations/{id}/resend)
    actualizará la row existente — acá generamos NUEVA siempre.

Rate-limit anti-bulk:

  - `invitation_send_rate_per_hour` (default 20) por actor — chequeado
    via bucket in-memory en `_invitation_rate_check`. Una sesión
    comprometida no puede mandar 1000 invitaciones a 1000 emails para
    spam phishing.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from app.core.config import get_settings
from app.services.email import (
    EmailMessage, EmailSendError, get_email_provider,
)
from app.services.email_templates import render_invitation_email

log = structlog.get_logger()


# ─── Exceptions ──────────────────────────────────────────────────────────


class InvitationRateLimitError(RuntimeError):
    """El actor excedió el límite de invitaciones por hora."""


class InvitationNotFoundError(LookupError):
    """No existe invitación con ese token (token inválido o falsificado)."""


class InvitationExpiredError(RuntimeError):
    """La invitación expiró (pasó `expires_at`)."""


class InvitationEmailMismatchError(RuntimeError):
    """El email del redimidor no coincide con el email de la invitación.

    Previene hijack: si alguien intercepta el link `/i/<token>`, no puede
    usarlo con SU propia cuenta de Auth0 para entrar al tenant del invitado
    original. El check es case-insensitive (DB usa `citext`)."""


# ─── Token generation ────────────────────────────────────────────────────


def generate_invitation_token() -> tuple[str, str]:
    """Devuelve `(clear_token, sha256_hash)`.

    `clear_token` va en la URL del email (NO en DB).
    `sha256_hash` se guarda en `tenant_invitations.token_hash` (lookup +
    verificación en el redemption endpoint).

    32 bytes random → 64 chars hex → ~256 bits de entropía. Sin partes
    predecibles ni timestamps embebidos.
    """
    raw = secrets.token_bytes(32)
    clear = raw.hex()
    h = hashlib.sha256(clear.encode('utf-8')).hexdigest()
    return clear, h


def hash_invitation_token(clear_token: str) -> str:
    """Recomputa el hash para lookup. Constant-time-safe a nivel cripto
    (sha256 mismo input → mismo output, no hay branching dependiente
    del input)."""
    return hashlib.sha256(clear_token.encode('utf-8')).hexdigest()


# ─── Rate limiting per actor ─────────────────────────────────────────────
#
# P1-3 (audit 2026-05-27) — migrado a `SlidingWindowLimiter` con cap+TTL
# para evitar growth ilimitado del dict (attack: N actor_ids sintéticos).
# El limiter se rebuilds lazy con el setting actual via `_get_limiter()`.

from app.services.sliding_window_rate_limit import (  # noqa: E402
    SlidingWindowLimiter, _build_sync_check,
)

_invitation_limiter: SlidingWindowLimiter | None = None


def _get_invitation_limiter() -> SlidingWindowLimiter:
    global _invitation_limiter
    settings = get_settings()
    # Rebuild si max_calls cambió (tests con overrides). En prod es
    # estable porque la setting no muta runtime.
    if (_invitation_limiter is None
            or _invitation_limiter.max_calls != settings.invitation_send_rate_per_hour):
        _invitation_limiter = SlidingWindowLimiter(
            max_calls=settings.invitation_send_rate_per_hour,
            window_seconds=3600.0,
        )
    return _invitation_limiter


def _invitation_rate_check(actor_id: str | None) -> None:
    """Levanta `InvitationRateLimitError` si el actor superó
    `invitation_send_rate_per_hour` invitaciones."""
    if not actor_id:
        return
    limiter = _get_invitation_limiter()
    if not _build_sync_check(limiter)(actor_id):
        raise InvitationRateLimitError(
            f'Excediste el límite de {limiter.max_calls} invitaciones por hora.'
            ' Esperá antes de mandar más.',
        )


def _reset_invitation_rate_buckets() -> None:
    """Test-only — limpia los buckets entre tests."""
    global _invitation_limiter
    if _invitation_limiter is not None:
        _invitation_limiter.reset()
    _invitation_limiter = None


# ─── DTOs ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InvitationSent:
    invitation_id: UUID
    accept_url: str
    expires_at: datetime
    email_message_id: str
    email_provider: str
    email_status: str  # 'queued' | 'noop' | 'failed'


# ─── Main entry point ───────────────────────────────────────────────────


async def create_and_send_invitation(
    *,
    conn: asyncpg.Connection,
    tenant_id: UUID,
    tenant_name: str,
    email: str,
    role: str,
    inviter_user_id: UUID | None,
    inviter_name: str | None = None,
    inviter_email: str | None = None,
) -> InvitationSent:
    """Crea la invitación + manda el email. Llamado desde
    `add_tenant_member` (también desde el endpoint de resend en
    iteración 2).

    No falla si el email no se entrega — la invitación queda persistida
    con `last_send_status='failed'` y el caller puede reintentar via
    el endpoint de resend. Esto evita que un downtime de Resend tumbe
    el flow de agregar miembros.
    """
    settings = get_settings()
    _invitation_rate_check(str(inviter_user_id) if inviter_user_id else None)

    clear_token, token_hash = generate_invitation_token()
    expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.invitation_token_ttl_seconds,
    )
    # `accept_url` = el link que ve el invitado. Iteración 2 implementa
    # `/i/<token>` en frontend + endpoint público para validar.
    accept_url = f'{settings.app_public_url.rstrip("/")}/i/{clear_token}'

    # ─── (1) INSERT invitation ────────────────────────────────────────
    # Idempotency: si ya existe una invitación PENDING para este
    # (tenant, email), la EXPIRAMOS y creamos una nueva. Esto soporta
    # el caso "el invitado perdió el email, admin re-invita".
    await conn.execute(
        '''
        update app.tenant_invitations
           set redeemed_at = now(),
               metadata = metadata || jsonb_build_object(
                 'superseded_at', to_jsonb(now()),
                 'reason', 'replaced_by_new_invite'
               )
         where tenant_id = $1 and email = $2 and redeemed_at is null
        ''',
        tenant_id, email,
    )
    row = await conn.fetchrow(
        '''
        insert into app.tenant_invitations
          (tenant_id, email, role, token_hash,
           invited_by_user_id, expires_at, sent_count, last_sent_at,
           last_send_status)
        values ($1, $2, $3, $4, $5, $6, 1, now(), 'queued')
        returning id, expires_at
        ''',
        tenant_id, email, role, token_hash, inviter_user_id, expires_at,
    )
    invitation_id: UUID = row['id']

    # ─── (2) Render template + send ──────────────────────────────────
    rendered = render_invitation_email(
        invitee_email=email,
        tenant_name=tenant_name,
        role=role,
        inviter_name=inviter_name,
        inviter_email=inviter_email,
        accept_url=accept_url,
        expires_in_days=max(1, settings.invitation_token_ttl_seconds // 86400),
    )

    provider = get_email_provider()
    headers: dict[str, str] = {}
    # Gmail 2024+ exige `List-Unsubscribe` en mass mail. Para transactional
    # no es obligatorio pero ayuda a deliverability.
    headers['List-Unsubscribe'] = f'<mailto:{settings.email_from_address}?subject=unsubscribe>'

    message = EmailMessage(
        to=email,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        reply_to=inviter_email or None,
        headers=headers,
        tags={
            'type': 'invitation',
            'tenant_id': str(tenant_id),
            'invitation_id': str(invitation_id),
        },
    )

    email_status = 'queued'
    email_message_id = ''
    email_provider_name = provider.name
    try:
        result = await provider.send(message)
        email_message_id = result.message_id
        email_status = 'queued' if result.delivered_at_provider else 'noop'
    except EmailSendError as exc:
        # No abortar el flow: la invitación queda persistida; el caller
        # puede reintentar (resend endpoint en iteración 2).
        email_status = 'failed'
        log.error(
            'invitation.email_send_failed',
            invitation_id=str(invitation_id),
            tenant_id=str(tenant_id),
            error=str(exc),
            status_code=getattr(exc, 'status_code', None),
        )

    # ─── (3) UPDATE con resultado del send ───────────────────────────
    await conn.execute(
        '''
        update app.tenant_invitations
           set last_send_provider_message_id = $1,
               last_send_status = $2,
               metadata = metadata || jsonb_build_object(
                 'provider', $3::text
               )
         where id = $4
        ''',
        email_message_id or None, email_status, email_provider_name,
        invitation_id,
    )

    log.info(
        'invitation.created',
        invitation_id=str(invitation_id),
        tenant_id=str(tenant_id),
        role=role,
        email_status=email_status,
        provider=email_provider_name,
        is_real_provider=provider.is_real(),
    )

    return InvitationSent(
        invitation_id=invitation_id,
        accept_url=accept_url,
        expires_at=row['expires_at'],
        email_message_id=email_message_id,
        email_provider=email_provider_name,
        email_status=email_status,
    )


# ─── Preview + Redeem (iteración 2 — endpoint /i/<token>) ──────────────


@dataclass(frozen=True)
class InvitationPreview:
    """Información pública (no-secret) de una invitación, suficiente para
    armar la landing page `/i/<token>` antes de que el invitado se logue.

    NO incluye el token, ni el hash, ni el inviter_user_id, ni metadata —
    solo lo que muestra la UI ("Te invitaron a TenantX como Y, link
    vigente hasta Z").
    """
    invitation_id: UUID
    tenant_id: UUID
    tenant_name: str
    role: str
    email: str  # del invitado (case-preserved como vino)
    expires_at: datetime
    redeemed: bool


def _row_to_preview(row: asyncpg.Record) -> InvitationPreview:
    return InvitationPreview(
        invitation_id=row['id'],
        tenant_id=row['tenant_id'],
        tenant_name=row['tenant_name'] or 'CopilotoIA',
        role=row['role'],
        email=row['email'],
        expires_at=row['expires_at'],
        redeemed=row['redeemed_at'] is not None,
    )


async def get_invitation_preview(
    conn: asyncpg.Connection, clear_token: str,
) -> InvitationPreview | None:
    """Lookup público para la landing page. Retorna `None` si no existe
    invitación con ese token (token falsificado o ya purgado).

    NO valida expiry — el caller decide qué mostrar al user (el handler
    público las muestra todas, marcando si están expiradas/redeemed). Sí
    consulta el flag `redeemed`.

    M66 — usa SECURITY DEFINER function `app.lookup_invitation_by_token_hash`
    para bypassar la RLS de `tenant_invitations`. El query directo
    devuelve 0 rows en endpoint público (sin tenant_id context). El
    secret del token actúa como auth para el lookup."""
    token_hash = hash_invitation_token(clear_token)
    row = await conn.fetchrow(
        'select * from app.lookup_invitation_by_token_hash($1)',
        token_hash,
    )
    if not row:
        return None
    return _row_to_preview(row)


async def redeem_invitation(
    *,
    conn: asyncpg.Connection,
    clear_token: str,
    redeemer_user_id: UUID,
    redeemer_email: str,
) -> InvitationPreview:
    """Marca la invitación como `redeemed_at = now()` y persiste el
    `redeemed_by_user_id`. Idempotente: si ya fue redimida por el mismo
    email, devuelve la preview sin error ni efecto secundario.

    Defensa anti-hijack:
      - Email mismatch → `InvitationEmailMismatchError`. Previene que un
        atacante que intercepta el link `/i/<token>` lo use con SU cuenta
        para entrar al tenant del invitado original.

    Validaciones:
      - Token existe → si no, `InvitationNotFoundError`.
      - Email matchea (case-insensitive) → si no, `InvitationEmailMismatchError`.
      - Si ya fue redeemed → idempotent (return).
      - Expiry chequeada solo en PRIMER redeem (already-redeemed son
        válidas aunque pasó `expires_at` — eso es un audit-log, no un gate).

    M66 — race-safety vía `app.mark_invitation_redeemed` (UPDATE con
    `where redeemed_at is null` que actúa como compare-and-swap). Si
    dos requests concurrentes redimen el mismo token, solo la primera
    afecta filas; la segunda observa el row ya marcado y entra al path
    idempotent."""
    token_hash = hash_invitation_token(clear_token)
    row = await conn.fetchrow(
        'select * from app.lookup_invitation_by_token_hash($1)',
        token_hash,
    )
    if not row:
        raise InvitationNotFoundError('invitation not found')

    # Email match (case-insensitive — DB col es `citext` pero igual
    # normalizamos en Python por defensa-en-profundidad).
    if row['email'].lower() != redeemer_email.lower():
        log.warning(
            'invitation.redeem.email_mismatch',
            invitation_id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            invitation_email_masked=row['email'][:2] + '***',
            redeemer_email_masked=redeemer_email[:2] + '***',
        )
        raise InvitationEmailMismatchError(
            'El email autenticado no coincide con el de la invitación.',
        )

    # Idempotent: ya redeemed por este mismo email → return preview.
    if row['redeemed_at'] is not None:
        log.info(
            'invitation.redeem.idempotent',
            invitation_id=str(row['id']),
            tenant_id=str(row['tenant_id']),
        )
        return _row_to_preview(row)

    # Expiry — solo en primer redeem.
    now = datetime.now(UTC)
    if row['expires_at'] < now:
        log.info(
            'invitation.redeem.expired',
            invitation_id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            expired_at=row['expires_at'].isoformat(),
        )
        raise InvitationExpiredError(
            f'La invitación expiró el {row["expires_at"].isoformat()}.',
        )

    await conn.fetchval(
        'select app.mark_invitation_redeemed($1, $2)',
        row['id'], redeemer_user_id,
    )

    log.info(
        'invitation.redeemed',
        invitation_id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        redeemer_user_id=str(redeemer_user_id),
    )

    # Construir preview con flag redeemed=True (sin segundo SELECT).
    return InvitationPreview(
        invitation_id=row['id'],
        tenant_id=row['tenant_id'],
        tenant_name=row['tenant_name'] or 'CopilotoIA',
        role=row['role'],
        email=row['email'],
        expires_at=row['expires_at'],
        redeemed=True,
    )


# ─── Internals exposed for testing ──────────────────────────────────────

_internal: dict[str, Any] = {
    # P1-3 — `rate_buckets` quedó como compatibility shim (callers que
    # esperaban el dict crudo ahora reciben el limiter object).
    'rate_buckets': lambda: _get_invitation_limiter()._buckets,  # noqa: SLF001
    'reset_rate_buckets': _reset_invitation_rate_buckets,
}
