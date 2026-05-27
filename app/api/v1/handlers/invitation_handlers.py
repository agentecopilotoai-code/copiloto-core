"""Handlers `/v1/invitations/*` — preview público + redemption (M65).

Endpoints:

  GET  /v1/invitations/{token}        — público (sin auth). Para que el
                                        BFF arme la landing page `/i/<t>`
                                        ANTES de exigir login.
  POST /v1/invitations/{token}/redeem — autenticado. El BFF lo llama
                                        después del OAuth callback,
                                        pasando el access_token del user
                                        recién logueado.

Diseño:

  - **GET es público pero opaco**: solo retorna info que el invitado YA
    conoce (tenant name, role, su propio email). No leak nada útil para
    enumeration attacks. Tokens son 256 bits random — tampoco hay
    brute-force viable.
  - **POST exige email-match**: el JWT del logueado debe traer un email
    que coincida con el de la invitación. Defiende contra "atacante
    intercepta el link y lo usa con SU cuenta para entrar al tenant".
  - **Idempotente**: si el user clickea 2 veces el link, el segundo POST
    devuelve 200 con `already_redeemed=true` (no falla).
  - **Expiry-friendly**: si la invitación expiró pero ya fue redeemed,
    sigue siendo válida (audit semantic — un "ya usaste el link" no
    debería romperse después de expirar).

Errores HTTP:
  - 404: token no existe.
  - 410 Gone: token válido pero expirado.
  - 403 Forbidden: email del JWT no matchea el de la invitación.
"""
from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.api.v1._helpers.me_utils import _require_current_user
from app.api.v1.routes import public_router, tenant_user_router
from app.db.pool import get_db
from app.services import invitations as invitations_service


def _preview_to_dict(preview: invitations_service.InvitationPreview) -> dict:
    return {
        'invitation_id': str(preview.invitation_id),
        'tenant_id': str(preview.tenant_id),
        'tenant_name': preview.tenant_name,
        'role': preview.role,
        'email': preview.email,
        'expires_at': preview.expires_at.isoformat(),
        'redeemed': preview.redeemed,
    }


@public_router.get('/invitations/{token}')
async def get_invitation(
    token: str,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Preview público de la invitación. El BFF lo llama desde `/i/<t>`
    SIN credenciales — el `token` opaco actúa como la auth de un solo
    uso.

    No 404ea "ruidosamente" para evitar enumeration: si el token no
    existe devolvemos 404 con un body neutro (no leak diferencia entre
    "no existe" vs "fue redeemed hace mucho")."""
    preview = await invitations_service.get_invitation_preview(conn, token)
    if preview is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Invitación no encontrada o ya fue procesada.',
        )
    return _preview_to_dict(preview)


@tenant_user_router.post('/invitations/{token}/redeem')
async def redeem_invitation(
    token: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Marca la invitación como redeemed para el user autenticado. Llamado
    por el BFF después del OAuth callback (cuando el user pasó del link
    `/i/<t>` → login → callback).

    El `actor_id` viene del JWT (Auth0 sub). El `email` viene del JWT
    (claim namespaced — ver A-003). Ambos requeridos."""
    user_id = await _require_current_user(request, conn)
    email = getattr(request.state, 'email', None)
    if not email:
        # JWT válido pero sin email → no podemos validar match. El user
        # debe re-loguearse para que el id_token traiga el claim.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='El token de sesión no incluye email. Re-iniciá sesión.',
        )

    try:
        preview = await invitations_service.redeem_invitation(
            conn=conn,
            clear_token=token,
            redeemer_user_id=user_id,
            redeemer_email=email,
        )
    except invitations_service.InvitationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Invitación no encontrada.',
        ) from exc
    except invitations_service.InvitationExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(exc),
        ) from exc
    except invitations_service.InvitationEmailMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return {
        **_preview_to_dict(preview),
        # `already_redeemed` distingue idempotent vs primer redeem
        # (útil para que el BFF/UI muestre mensajes distintos).
        'already_redeemed': preview.redeemed,
    }
