"""Fix-group 40: Codex Security HIGH+MEDIUM — extraction worker trust + SSRF.

- **BUG-213** (HIGH, `app/workers/extraction_worker.py`): el worker consumía
  `metadata.storage_backend`, `metadata.storage_bucket` y `metadata.storage_key`
  directamente — todos campos tenant-writable via PATCH del knowledge doc.
  Un tenant admin malicioso podía crear/PATCH un doc con `storage_key`
  apuntando al bucket/prefix de OTRO tenant, y el worker (que corre con
  `app.support_mode` bypaseando RLS) leía el archivo cross-tenant y
  persistía su `extracted_text` en metadata del documento del atacante.
- **BUG-214** (MEDIUM, `app/services/url_guard.py`): `_PRIVATE_NETWORKS` solo
  incluía `::ffff:127.0.0.0/104` (IPv4-mapped loopback). Pero IPv6 puede
  expresar TODAS las RFC1918 / link-local ranges via `::ffff:<v4>`. Un
  tenant admin podía configurar webhook URL `https://[::ffff:169.254.169.254]/...`
  y bypassear el SSRF guard hacia el AWS metadata service. Agregadas las
  variantes IPv4-mapped restantes + helper `ipv4_mapped` check de
  defense-in-depth.
"""
from __future__ import annotations

from pathlib import Path


URL_GUARD = Path('app/services/url_guard.py')
EXTRACTION = Path('app/workers/extraction_worker.py')


# ───── BUG-213 — extraction worker trust ────────────────────────────────


def test_bug_213_load_file_bytes_takes_tenant_id_param():
    src = EXTRACTION.read_text()
    assert 'async def _load_file_bytes(' in src
    # P1 follow-up: signature now multi-line with tenant_id + tenant_storage_config.
    assert 'tenant_id: Any,' in src, (
        'BUG-213: `_load_file_bytes` debe aceptar `tenant_id` keyword-only '
        '(viene del row de DB, NO de metadata).'
    )
    assert 'tenant_storage_config: dict[str, Any] | None = None' in src, (
        'BUG-213 P1 follow-up: `_load_file_bytes` debe aceptar '
        '`tenant_storage_config` para usar el backend/bucket/prefix del '
        'tenant (no hardcoded global).'
    )


def test_bug_213_load_file_bytes_validates_storage_key_prefix():
    src = EXTRACTION.read_text()
    fn_idx = src.find('async def _load_file_bytes(')
    next_def = src.find('\nasync def ', fn_idx + 1)
    block = src[fn_idx:next_def]
    # P2 follow-up: el prefix viene de `tenant_storage_config['prefix']` (con
    # fallback `tenants/<tenant_id>/knowledge`); aceptamos cualquier path en
    # tanto venga de la trusted source, no hardcoded `tenants/<tenant_id>/`.
    assert 'trusted_prefix' in block, (
        'BUG-213 + P2 follow-up: debe existir `trusted_prefix` derivado de '
        '`tenant_storage_config[\'prefix\']` (DB-trusted) o fallback al '
        'patrón legacy `tenants/<tenant_id>/knowledge`.'
    )
    assert "expected_prefix = trusted_prefix.rstrip('/') + '/'" in block, (
        'BUG-213: el `expected_prefix` debe normalizarse con trailing slash '
        'para evitar matches parciales.'
    )
    assert 'if not storage_key.startswith(expected_prefix):' in block, (
        'BUG-213: si el `storage_key` no empieza con el prefix esperado, '
        'el worker debe levantar ValueError (rechazo cross-tenant).'
    )


def test_bug_213_load_file_bytes_does_not_trust_metadata_for_backend():
    src = EXTRACTION.read_text()
    fn_idx = src.find('async def _load_file_bytes(')
    next_def = src.find('\nasync def ', fn_idx + 1)
    block = src[fn_idx:next_def]
    # NO debe trustear metadata.storage_backend ni storage_bucket.
    assert "metadata.get('storage_backend')" not in block, (
        'BUG-213: el backend ya NO debe venir de `metadata.storage_backend` — '
        'usar `tenant_storage_config[\'backend\']` (DB) o settings global.'
    )
    assert "metadata.get('storage_bucket')" not in block, (
        'BUG-213: el bucket ya NO debe venir de `metadata.storage_bucket` — '
        'usar `tenant_storage_config[\'bucket\']` (DB) o settings global.'
    )


def test_bug_213_caller_passes_tenant_id_and_storage_config():
    src = EXTRACTION.read_text()
    # P1 follow-up: el caller debe pasar también `tenant_storage_config` para
    # que el worker use el backend tenant (no hardcoded global).
    assert 'tenant_storage_config=tenant_storage_config' in src, (
        'BUG-213 P1 follow-up: el caller en `_process_document` debe pasar '
        'el `tenant_storage_config` resuelto de la DB tenant_settings.'
    )
    assert 'fetch_tenant_knowledge_storage_config' in src, (
        'BUG-213 P1 follow-up: el worker debe llamar '
        '`fetch_tenant_knowledge_storage_config(conn, tenant_id)` para resolver '
        'la config trusted (mismo helper que el upload).'
    )


# ───── BUG-214 — SSRF guard IPv4-mapped private ranges ──────────────────


def test_bug_214_private_networks_include_ipv4_mapped_rfc1918():
    src = URL_GUARD.read_text()
    fn_idx = src.find('_PRIVATE_NETWORKS')
    end = src.find(')\n\n', fn_idx)
    block = src[fn_idx:end]
    # Loopback was already there.
    assert "ipaddress.ip_network('::ffff:127.0.0.0/104')" in block
    # Nuevas variantes que cubre el fix.
    assert "ipaddress.ip_network('::ffff:10.0.0.0/104')" in block, (
        'BUG-214: debe bloquear IPv4-mapped RFC1918 class A.'
    )
    assert "ipaddress.ip_network('::ffff:172.16.0.0/108')" in block, (
        'BUG-214: debe bloquear IPv4-mapped RFC1918 class B.'
    )
    assert "ipaddress.ip_network('::ffff:192.168.0.0/112')" in block, (
        'BUG-214: debe bloquear IPv4-mapped RFC1918 class C.'
    )
    assert "ipaddress.ip_network('::ffff:169.254.0.0/112')" in block, (
        'BUG-214: debe bloquear IPv4-mapped link-local (AWS metadata).'
    )


def test_bug_214_ip_is_blocked_uses_ipv4_mapped_check():
    src = URL_GUARD.read_text()
    fn_idx = src.find('def _ip_is_blocked(')
    next_def = src.find('\ndef validate_outbound_url(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'ip.ipv4_mapped is not None' in block, (
        'BUG-214: defense-in-depth — además de las redes enumeradas, debe '
        'chequear `ip.ipv4_mapped` para casos donde la dirección llegue '
        'ya parseada como IPv6Address sin matchear los nets exactos.'
    )


def test_bug_214_ipv4_mapped_metadata_address_is_blocked():
    """Smoke test: la dirección AWS metadata vía IPv4-mapped IPv6 debe ser
    bloqueada por el helper directo (no requiere DNS resolution)."""
    import ipaddress
    from app.services.url_guard import _ip_is_blocked

    metadata_v4 = ipaddress.IPv4Address('169.254.169.254')
    assert _ip_is_blocked(metadata_v4), 'AWS metadata IP must be blocked (sanity)'

    metadata_v6_mapped = ipaddress.IPv6Address('::ffff:169.254.169.254')
    assert _ip_is_blocked(metadata_v6_mapped), (
        'BUG-214: la AWS metadata IP expresada como IPv4-mapped IPv6 '
        '(`::ffff:169.254.169.254`) debe ser bloqueada.'
    )
