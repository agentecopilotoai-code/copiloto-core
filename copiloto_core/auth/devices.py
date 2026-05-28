"""HMAC verification para devices (IoT) + webhooks firmados.

Diferente al flujo Auth0 OIDC humano: acá un device físico (un
controlador IoT, un webhook de provider externo) firma cada request
con un secret pre-compartido. El core valida la firma con
**constant-time compare** y devuelve la identidad asociada al secret.

# Uso típico

```python
from fastapi import APIRouter, Depends
from copiloto_core.auth.devices import verify_device_hmac

router = APIRouter()

async def _lookup_secret(device_id: str) -> str | None:
    # El módulo decide cómo resolver: DB lookup, KV store, env, etc.
    async with db.connection() as conn:
        row = await conn.fetchrow(
            'select hmac_secret from mi_modulo.devices where id = $1', device_id,
        )
        return row['hmac_secret'] if row else None

@router.post("/v1/mi-modulo/ingest")
async def ingest(
    payload: TelemetryBatch,
    device = Depends(verify_device_hmac(_lookup_secret)),
):
    # device.device_id es el id verificado
    ...
```

# Wire format esperado

El device envía 2 headers:

  X-Device-Id:        identificador opaco del device
  X-Device-Signature: hex(hmac_sha256(secret, request.body))

El core lee `X-Device-Id`, llama `secret_lookup(device_id)` para
obtener el secret, computa HMAC del body, compara constant-time con
la firma del header.

# Reemplazos en lugar de implementar otros HMAC schemes

NO soportamos:
- Resend/Stripe/GitHub webhook signature formats (cada uno tiene el
  suyo). Si necesitás esos, escribí un helper específico en el módulo
  con su propio formato — `verify_device_hmac` es genérico.
- Timestamp anti-replay nonce (que harían sí un `X-Device-Timestamp`).
  Si el módulo lo necesita, puede componer este helper con su propio
  Depends que valide el timestamp ANTES.

# Rationale del diseño

- `secret_lookup` es callable async → el módulo decide la fuente del
  secret (DB con cache, env var por device, vault).
- El verifier es factory que devuelve Depends → tipado FastAPI claro.
- Constant-time compare via `hmac.compare_digest` → resistente a
  timing attacks.
- 401 si el header falta, 401 si la firma no matchea — NUNCA 403
  (no revelamos si el device existe o no).
"""
from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


# Headers obligatorios del wire format.
HEADER_DEVICE_ID = 'X-Device-Id'
HEADER_DEVICE_SIGNATURE = 'X-Device-Signature'


@dataclass(frozen=True)
class DeviceIdentity:
    """Identidad resuelta del device tras verificar HMAC.

    Attrs:
      device_id: el identificador opaco que envió el device en el
        header `X-Device-Id`. Verificado por el HMAC.
    """

    device_id: str


# Firma del secret lookup que el módulo provee.
DeviceSecretLookup = Callable[[str], Awaitable[str | None]]


def verify_device_hmac(
    secret_lookup: DeviceSecretLookup,
    *,
    header_device_id: str = HEADER_DEVICE_ID,
    header_signature: str = HEADER_DEVICE_SIGNATURE,
) -> Callable[..., Awaitable[DeviceIdentity]]:
    """Factory que devuelve un `Depends` validando HMAC del body.

    Args:
      secret_lookup: callable async `(device_id) -> secret | None`
        que el módulo provee. Retorna `None` si el device_id no es
        conocido (el factory levanta 401 por seguridad).
      header_device_id: nombre del header con el device id. Default
        `X-Device-Id`. Permite override por consistencia con otros
        protocolos del módulo.
      header_signature: nombre del header con la firma hex. Default
        `X-Device-Signature`. Idem.

    Returns:
      Async function usable como `Depends(...)` que devuelve
      `DeviceIdentity` al handler.

    Raises (vía HTTPException 401):
      - `device_id_missing` si falta el header X-Device-Id.
      - `signature_missing` si falta X-Device-Signature.
      - `device_unauthorized` si el device_id no resuelve a secret
        (NO discrimina entre device-no-existe vs secret-roto, anti-enum).
      - `signature_invalid` si la firma no matchea el HMAC del body.
    """

    async def _verifier(request: Request) -> DeviceIdentity:
        device_id = request.headers.get(header_device_id)
        if not device_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={'error': 'device_id_missing',
                        'message': f'header {header_device_id} requerido'},
            )

        signature_hex = request.headers.get(header_signature)
        if not signature_hex:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={'error': 'signature_missing',
                        'message': f'header {header_signature} requerido'},
            )

        secret = await secret_lookup(device_id)
        if secret is None:
            # ANTI-enumeration: mismo error que signature_invalid, no
            # revelamos si el device existe o no.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={'error': 'device_unauthorized',
                        'message': 'device unknown or invalid signature'},
            )

        body = await request.body()
        expected = hmac.new(
            secret.encode('utf-8'),
            msg=body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature_hex.lower()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={'error': 'device_unauthorized',
                        'message': 'device unknown or invalid signature'},
            )

        return DeviceIdentity(device_id=device_id)

    return _verifier


__all__ = [
    'DeviceIdentity',
    'DeviceSecretLookup',
    'HEADER_DEVICE_ID',
    'HEADER_DEVICE_SIGNATURE',
    'verify_device_hmac',
]
