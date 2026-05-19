"""Fix-group 42: Codex Security MEDIUM — DoS unbounded resources.

Cierra los bugs surgical (BUG-49 WhatsApp media proxy, BUG-50 WS pool) que
requieren refactor más invasivo quedan diferidos a fix-group-44.

- **BUG-219** (MEDIUM, `app/services/rate_limit.py`): `extract_client_ip`
  trusteaba X-Forwarded-For UNCONDICIONALMENTE — atacante rotaba el
  header en cada request, generando nuevas keys del bucket y bypaseando
  el rate limit. Fix: nueva config `trust_proxy_forwarded_for` (default
  False) — solo lee XFF cuando el operador confirmó que hay un reverse
  proxy strip+reinject delante.
- **BUG-220** (MEDIUM, `app/api/v1/schemas.py`): `ContactTagAssign.tag_ids`
  era unbounded. Agent malicioso podía mandar 10M UUIDs forzando 10M
  iteraciones de SELECT+INSERT+audit. Fix: `max_length=50`.
- **BUG-221** (MEDIUM, `app/api/v1/routes.py:get_conversation`): retry
  loop con `asyncio.sleep(0.1)` mantenía la pool conn ~400ms por
  request. Atacante con UUIDs random saturaba la pool (`max_size=10`).
  Fix: single query, 404 inmediato — el retry race del legacy se
  maneja client-side.
- **BUG-222** (MEDIUM, `app/api/v1/routes.py` media upload): pre-check
  de Content-Length contra `MEDIA_SIZE_LIMITS_BYTES[kind]` antes de
  leer body — evita buffer de GB en memoria pre-rejection.
- **BUG-223** (MEDIUM, `app/api/v1/routes.py` knowledge upload): mismo
  pre-check contra `knowledge_file_max_bytes`.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


RATE_LIMIT = Path('app/services/rate_limit.py')
SCHEMAS = Path('app/api/v1/schemas.py')
CONFIG = Path('app/core/config.py')


def test_bug_219_extract_client_ip_gated_by_trust_proxy_setting():
    src = RATE_LIMIT.read_text()
    fn_idx = src.find('def extract_client_ip(')
    next_def = src.find('\ndef build_rate_limit_middleware', fn_idx)
    block = src[fn_idx:next_def]
    assert "getattr(settings, 'trust_proxy_forwarded_for', False)" in block, (
        'BUG-219: `extract_client_ip` debe consultar `trust_proxy_forwarded_for` '
        'del settings antes de leer X-Forwarded-For.'
    )
    assert 'if trust_xff:' in block, (
        'BUG-219: la lectura de XFF debe estar gateada por la variable trust_xff.'
    )


def test_bug_219_config_exposes_trust_proxy_toggle():
    src = CONFIG.read_text()
    assert 'trust_proxy_forwarded_for: bool = False' in src, (
        'BUG-219: `Settings` debe exponer `trust_proxy_forwarded_for: bool = False` '
        'con default conservador (no trust).'
    )


def test_bug_220_contact_tag_assign_caps_max_length():
    src = SCHEMAS.read_text()
    assert 'tag_ids: list[UUID] = Field(default_factory=list, max_length=50)' in src, (
        'BUG-220: `ContactTagAssign.tag_ids` debe tener `max_length=50` para '
        'evitar DoS por unbounded list iteration.'
    )


def test_bug_221_get_conversation_drops_retry_sleep_loop():
    src = routes_aggregated_source()
    fn_idx = src.find('async def get_conversation(')
    next_fn = src.find('\n@tenant_ops_router', fn_idx + 10)
    block = src[fn_idx:next_fn]
    assert 'for attempt in range(5):' not in block, (
        'BUG-221: el retry loop legacy debe eliminarse (causaba pool '
        'exhaustion bajo carga maliciosa).'
    )
    assert 'await asyncio.sleep(0.1)' not in block, (
        'BUG-221: el sleep dentro del retry loop debe eliminarse.'
    )


def test_bug_222_media_upload_precheck_content_length():
    src = routes_aggregated_source()
    # Buscar el bloque del media upload — heuristic: `MEDIA_SIZE_LIMITS_BYTES`.
    assert 'from app.services.media_storage import MEDIA_SIZE_LIMITS_BYTES as _MEDIA_CAPS' in src, (
        'BUG-222: el media upload debe importar `MEDIA_SIZE_LIMITS_BYTES` '
        'para el pre-check.'
    )
    assert "request.headers.get('content-length')" in src, (
        'BUG-222: el pre-check debe leer el header `content-length`.'
    )


def test_bug_223_knowledge_upload_precheck_content_length():
    src = routes_aggregated_source()
    # El comment del BUG-223 es señal específica.
    assert 'BUG-223' in src and 'knowledge_file_max_bytes * 2' in src, (
        'BUG-223: el knowledge upload debe comparar `content-length` contra '
        '`knowledge_file_max_bytes * 2` (2x slack para multipart) antes de leer.'
    )
