"""Fix-group 44: Codex Reviews follow-up sobre PRs #61, #62, #63 mergeados.

Reviews del bot Codex que llegaron POST-merge en PRs ya cerrados; quedaron
sin atender hasta este fix-group consolidado.

- **BUG-228** (codex P1 sobre PR #61): el fix de BUG-195 dropeó el header
  `X-Admin-User-Email` completamente. Pero Auth0 PostLogin Action NO agrega
  claim `email` al access token (solo a id_token). Para requests normales
  del panel `request.state.email` queda vacío → fallback escribía
  `<hash>@auth.local` → al invitar a un email real, el lookup por email
  fallaba y los pending-invite no se reclamaban. Regresión real del admin
  flow. Fix: header `X-Admin-Identity` firmado con `pack_signed_payload`
  desde el BFF; el Core valida firma + sub match + exp antes de aceptar
  el email. Un caller con bearer token directo NO puede producirlo
  (no tiene `jwt_secret`).
- **BUG-229** (codex P2 sobre PR #62): el check de `cookie_matches_request`
  en `deactivate_support_mode` ignoraba el campo `exp`. Cliente replaying
  cookie viejo con `sub`+`tid` correctos pero `exp` ya pasado seguía
  triggereando audit `support_mode.deactivated`. Fix: validar
  `cookie_exp > now_ts`.
- **BUG-230** (codex P1 sobre PR #63): `verify_mercadopago_signature` solo
  validaba freshness `if now_ts and ts:` — si el header MP omite `ts`,
  el verifier caía al fallback de raw-payload HMAC y aceptaba el
  firmado indefinidamente. Atacante que strippea `ts` bypasea el fix de
  replay. Fix: cuando `now_ts is not None`, REQUERIR `ts` (fail-closed
  sin freshness data).
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


ADMIN_ROUTES = Path('app/admin/routes.py')
PAYMENT_PROVIDER = Path('app/services/payment_provider.py')


# ───── BUG-228 — restore signed BFF email header ────────────────────────


def test_bug_228_user_email_falls_back_to_signed_bff_header():
    src = routes_aggregated_source()
    fn_idx = src.find('def user_email_from_request(request: Request) -> str:')
    assert fn_idx > 0
    next_fn = src.find('\ndef _email_from_signed_bff_header(', fn_idx)
    block = src[fn_idx:next_fn]
    assert '_email_from_signed_bff_header(request)' in block, (
        'BUG-228: `user_email_from_request` debe intentar el header firmado '
        'del BFF como fallback antes del sintético.'
    )


def test_bug_228_signed_header_validator_exists():
    src = routes_aggregated_source()
    fn_idx = src.find('def _email_from_signed_bff_header(request: Request) -> str | None:')
    assert fn_idx > 0, (
        'BUG-228: debe existir el helper `_email_from_signed_bff_header`.'
    )
    next_def = src.find('\ndef user_display_name_from_request', fn_idx)
    block = src[fn_idx:next_def]
    assert "request.headers.get('X-Admin-Identity')" in block, (
        'BUG-228: el helper debe leer el header `X-Admin-Identity`.'
    )
    assert 'unpack_signed_payload(settings.jwt_secret, raw)' in block, (
        'BUG-228: el helper debe desempaquetar el payload firmado con '
        '`jwt_secret` — un caller bearer directo NO tiene el secret.'
    )
    assert "sub != getattr(request.state, 'actor_id', None)" in block, (
        'BUG-228: el `sub` del payload debe matchear el `actor_id` del JWT '
        '(no aceptar emails para `sub` que el caller no controla).'
    )
    assert 'exp <= now_ts' in block, (
        'BUG-228: el payload debe tener `exp > now` (rechazo de replay).'
    )


def test_bug_228_bff_emits_signed_identity_header():
    src = ADMIN_ROUTES.read_text()
    fn_idx = src.find('def _core_api_headers(')
    assert fn_idx > 0
    next_def = src.find('\ndef _namespaced_claim(', fn_idx)
    block = src[fn_idx:next_def]
    assert "headers['x-admin-identity']" in block, (
        'BUG-228: el BFF debe emitir el header `x-admin-identity` con el '
        'payload firmado.'
    )
    assert 'pack_signed_payload(jwt_secret, identity_payload)' in block, (
        'BUG-228: el BFF debe usar `pack_signed_payload` (mismo helper que '
        'el cookie de support_mode) con `jwt_secret`.'
    )
    assert "'sub': sub, 'email': email, 'exp': exp_ts" in block, (
        'BUG-228: el payload firmado debe incluir `{sub, email, exp}`.'
    )


# ───── BUG-229 — cookie exp validation antes del audit ─────────────────


def test_bug_229_deactivate_support_mode_validates_cookie_exp():
    src = routes_aggregated_source()
    fn_idx = src.find('async def deactivate_support_mode(')
    assert fn_idx > 0
    next_fn = src.find('\nweb_router = ', fn_idx)
    block = src[fn_idx:next_fn]
    assert "cookie_exp = cookie_payload.get('exp')" in block, (
        'BUG-229: el handler debe extraer `cookie_exp` del payload.'
    )
    assert 'isinstance(cookie_exp, int)' in block and 'cookie_exp > now_ts' in block, (
        'BUG-229: el match debe exigir `cookie_exp > now_ts` además de '
        '`tid`+`sub`. Sin esto, un cookie expirado replayed seguía contando '
        'como match y triggereaba audit deactivation.'
    )


# ───── BUG-230 — MP verifier requiere ts cuando now_ts provisto ─────────


def test_bug_230_mp_verifier_requires_ts_when_now_ts_supplied():
    src = PAYMENT_PROVIDER.read_text()
    fn_idx = src.find('def verify_mercadopago_signature(')
    assert fn_idx > 0
    next_def = src.find('\ndef verify_stripe_signature(', fn_idx)
    block = src[fn_idx:next_def]
    # El check ya NO debe ser `if now_ts is not None and ts:` (que skippeaba
    # el bloque entero cuando `ts` no estaba).
    assert 'if now_ts is not None and ts:' not in block, (
        'BUG-230: el check legacy `if now_ts is not None and ts:` debe '
        'reemplazarse por uno que falle si `ts` no está.'
    )
    # Nuevo patrón fail-closed: si caller pide freshness, exigir ts.
    assert 'if now_ts is not None:' in block, (
        'BUG-230: el verifier debe entrar al bloque cuando `now_ts` se '
        'pasa, independientemente de si el header trae `ts`.'
    )
    assert 'if not ts:\n            return False' in block, (
        'BUG-230: dentro del bloque, si el header NO trae `ts` y el caller '
        'pidió freshness, debe fail-closed (return False).'
    )


def test_bug_230_mp_verifier_runtime_rejects_missing_ts_when_now_ts_set():
    """Smoke test: el verifier rechaza inmediatamente cuando now_ts está
    seteado y el header NO trae ts (no permite caer al raw payload fallback)."""
    from app.services.payment_provider import verify_mercadopago_signature
    body = b'{"id":123,"status":"paid"}'
    # Header sin `ts=`, solo `v1=`.
    header = 'v1=deadbeef'
    secret = 'test-secret'
    # Sin now_ts (legacy): debería intentar el fallback y devolver False
    # (HMAC no matchea), pero NO fail-closed por missing ts.
    assert verify_mercadopago_signature(body, header, secret) is False
    # Con now_ts: fail-closed por missing ts ANTES de comparar HMAC.
    assert verify_mercadopago_signature(body, header, secret, now_ts=1700000000) is False
