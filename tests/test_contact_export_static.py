"""SEC-010-EXPORT-FU: tests estáticos para el endpoint contact-scoped de
extracto de consent ledger.

Antes de este endpoint, las reclamaciones de "derecho de acceso" (Ley 1581 /
GDPR) sobre un único contacto se atendían así:
  1. Operador corre `GET /v1/tenants/{id}/data-export` (tenant-wide).
  2. Operador hace `jq` / `grep` para aislar las filas del contacto.
  3. Operador entrega ese JSON al claimant.

El runbook `consent-violation-claim.md` cerró ese path en SEC-010 (sub-finding
6317cdc8) porque entregar el dump tenant-wide es un leak masivo de PII de
TODOS los demás contactos — una violación peor que la original.

Como workaround intermedio el runbook pedía componer el extracto via SQL
ad-hoc. Este endpoint lo reemplaza con un handler server-side firmado,
auditado y testeado.

Los tests son AST-based / source-grep para que sigan corriendo en cualquier
entorno (sin DB) y para que defiendan las propiedades que no pueden ser
"verdaderas por accidente": el handler está en el router correcto, valida el
contacto, los `kinds` están limitados a la allowlist, firma con HMAC, audita
con la action correcta, y NUNCA emite SQL sin filtrar por `tenant_id`.
"""
from __future__ import annotations

import inspect
import textwrap

from app.api.v1 import routes as routes_module
from app.core import export_signatures


def _source_of(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(routes_module, name)))


def _source_of_export_signatures(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(export_signatures, name)))


# ───── Existencia + montaje en el router correcto ────────────────────────


def test_export_contact_data_handler_exists():
    """Anchor básico: si alguien renombra el handler, falla acá."""
    assert hasattr(routes_module, 'export_contact_data'), (
        'SEC-010-EXPORT-FU: el handler `export_contact_data` debe existir en '
        'app/api/v1/routes.py.'
    )


def test_export_endpoint_mounted_on_tenant_admin_router():
    """tenant_admin_router exige `require_min_role('admin')` — manager/agent/
    viewer reciben 403 antes del handler. Si por error se monta en
    tenant_ops_router (agent+) o tenant_signup_router (anónimo), un agente
    podría dumpear el extracto de cualquier contacto.
    """
    source = _source_of('export_contact_data')
    # El decorador de FastAPI no aparece en getsource(handler), así que
    # vamos al source completo del módulo para verificarlo.
    full = inspect.getsource(routes_module)
    decorator_idx = full.find(
        "@tenant_admin_router.get('/tenants/{tenant_id}/contacts/{contact_id}/export')"
    )
    assert decorator_idx >= 0, (
        'SEC-010-EXPORT-FU: el endpoint debe montarse exactamente en '
        "@tenant_admin_router.get('/tenants/{tenant_id}/contacts/{contact_id}/export') "
        '— cualquier otro router (ops/anonymous) deja entrar roles inferiores.'
    )
    # Y el siguiente bloque debe ser `async def export_contact_data`:
    handler_idx = full.find('async def export_contact_data', decorator_idx)
    assert handler_idx > decorator_idx, (
        'SEC-010-EXPORT-FU: el decorador del export debe estar pegado al handler '
        'export_contact_data (sin otro endpoint en el medio).'
    )
    assert source  # asegura que _source_of resolvió bien


# ───── Allowlist de `kinds` (no inyección de tablas arbitrarias) ─────────


def test_kinds_allowlist_is_closed():
    """`_CONTACT_EXPORT_ALLOWED_KINDS` debe ser un tuple/lista cerrada. Si
    alguien la convierte en `set()` mutable o la genera dinámicamente, se
    abre la puerta a SQL builder bugs o a kinds que no fueron auditados.
    """
    allowed = getattr(routes_module, '_CONTACT_EXPORT_ALLOWED_KINDS', None)
    assert allowed is not None, (
        'SEC-010-EXPORT-FU: la constante `_CONTACT_EXPORT_ALLOWED_KINDS` debe '
        'existir y ser la única fuente de verdad de los kinds soportados.'
    )
    assert isinstance(allowed, tuple), (
        'SEC-010-EXPORT-FU: _CONTACT_EXPORT_ALLOWED_KINDS debe ser tuple '
        '(inmutable) — set/list permitiría mutación accidental.'
    )
    # El alcance del backlog dice: consent_ledger, messages, opcional appts/subs.
    assert 'consent_ledger' in allowed
    assert 'messages' in allowed


def test_handler_rejects_unknown_kinds_with_422():
    """El handler debe validar `kinds` ANTES de tocar la DB. Sin esta guarda,
    `kinds=evil_table` pasaría al SQL builder y o bien revienta con un 500
    (mala UX) o, peor, en algún refactor futuro se vuelve inyectable.
    """
    source = _source_of('export_contact_data')
    assert 'status_code=422' in source, (
        'SEC-010-EXPORT-FU: kinds inválidos deben rechazarse con 422.'
    )
    assert '_CONTACT_EXPORT_ALLOWED_KINDS' in source, (
        'SEC-010-EXPORT-FU: la validación de kinds debe usar la constante '
        '_CONTACT_EXPORT_ALLOWED_KINDS — no hardcodear strings en el handler.'
    )
    # La validación tiene que correr ANTES del primer SELECT (sino la DB
    # también queda expuesta al kind malo y la auditoría suma ruido).
    invalid_check_idx = source.find('Invalid kinds')
    first_select_idx = source.find('from app.contacts')
    assert 0 <= invalid_check_idx < first_select_idx, (
        'SEC-010-EXPORT-FU: la validación de kinds debe correr ANTES del '
        'primer SELECT (incluido el lookup del contacto).'
    )


def test_handler_rejects_empty_kinds_with_422():
    """`?kinds=` o `?kinds=,,` no debe producir un bundle vacío firmado — eso
    sería un export "exitoso" sin contenido que pasa por el audit log y
    confunde la forensia. Mejor 422 explícito.
    """
    source = _source_of('export_contact_data')
    assert 'At least one kind is required' in source, (
        'SEC-010-EXPORT-FU: kinds vacío debe rechazarse con 422 explícito.'
    )


# ───── Validación de contacto + tenant scoping ───────────────────────────


def test_handler_requires_tenant_access():
    """`ensure_tenant_access` evita que un admin de tenant A pase un
    tenant_id de B en la URL. Defense-in-depth sobre el router (que ya
    requiere admin) y sobre RLS (que filtra por GUC).
    """
    source = _source_of('export_contact_data')
    assert 'await ensure_tenant_access(request, tenant_id, conn)' in source, (
        'SEC-010-EXPORT-FU: el handler debe invocar ensure_tenant_access antes '
        'de cualquier consulta — sin esto, un admin de tenant A puede pasar '
        'un tenant_id de B y la única defensa restante es RLS (capa única).'
    )


def test_handler_sets_rls_guc():
    """Necesario para que RLS actúe sobre las consultas siguientes. Olvidar
    este `set_config` deja al fetch del contacto y los kinds confiando solo
    en el `WHERE tenant_id=$1` explícito (peligroso si alguien lo borra).
    """
    source = _source_of('export_contact_data')
    assert "set_config('app.tenant_id'" in source, (
        'SEC-010-EXPORT-FU: el handler debe setear `app.tenant_id` GUC para '
        'que RLS aplique. Defense-in-depth sobre el WHERE explícito.'
    )


def test_handler_404s_when_contact_not_in_tenant():
    """El lookup del contacto filtra por `tenant_id=$1 and id=$2` y devuelve
    404 si no matchea. Sin esto, un admin podría pasar un contact_id que
    pertenece a OTRO tenant y aunque RLS filtre, el handler raisearía un
    NoneType subscript en algún path posterior.
    """
    source = _source_of('export_contact_data')
    assert 'where tenant_id=$1 and id=$2' in source, (
        'SEC-010-EXPORT-FU: el SELECT inicial del contacto debe filtrar por '
        'tenant_id AND id para descartar IDs de otro tenant antes de seguir.'
    )
    assert "status_code=404" in source and 'Contact not found' in source, (
        'SEC-010-EXPORT-FU: contacto no encontrado debe responder 404 explícito.'
    )


def test_all_queries_filter_by_tenant_id():
    """Cada SELECT del handler debe llevar `tenant_id=$1` en el WHERE. Esta
    es la guarda más crítica del endpoint: una sola query sin tenant_id =
    leak cross-tenant masivo. RLS catchea, pero NO confiamos sólo en RLS.
    """
    source = _source_of('export_contact_data')
    # Cuento ocurrencias de SELECT y de tenant_id en clauses WHERE.
    selects = source.lower().count('select ')
    where_tenant = source.lower().count('where tenant_id=$1') + source.lower().count(
        'where m.tenant_id=$1'
    )
    assert selects >= 4, (
        'SEC-010-EXPORT-FU: esperamos al menos 4 SELECTs (contact + 3 de los '
        'kinds que el alcance soporta). Si redujiste, ajusta el test.'
    )
    assert where_tenant >= 4, (
        f'SEC-010-EXPORT-FU: TODAS las queries deben filtrar por tenant_id '
        f'(esperaba ≥4 ocurrencias de `where ... tenant_id=$1`, encontré '
        f'{where_tenant}). Cualquier SELECT sin tenant filter abre leak '
        f'cross-tenant — RLS catchea pero NO debe ser la única defensa.'
    )


def test_messages_query_joins_via_conversations_with_double_tenant_check():
    """`app.messages` no tiene `contact_id` directo (el conversation owns the
    relación). Hay que joinear via `conversations` Y filtrar tenant_id en
    AMBAS sides para defenderse del (imposible-pero-paranoia) caso de un
    conversation_id apuntando a otro tenant.
    """
    source = _source_of('export_contact_data')
    assert 'join app.conversations c on c.id = m.conversation_id' in source, (
        'SEC-010-EXPORT-FU: la query de messages debe joinear via '
        'app.conversations (messages no tiene contact_id directo).'
    )
    assert 'm.tenant_id=$1 and c.tenant_id=$1' in source, (
        'SEC-010-EXPORT-FU: la query de messages debe filtrar tenant_id en '
        'AMBAS tablas (m + c) — defense-in-depth contra conversations '
        'cross-tenant.'
    )


# ───── Firma HMAC ────────────────────────────────────────────────────────


def test_sign_export_bundle_helper_uses_hmac_sha256_under_jwt_secret():
    """El helper de firma debe usar HMAC-SHA256 bajo `settings.jwt_secret`.
    Cambios accidentales a un hash plano (sha256(content)) destruyen la
    propiedad de "no se puede regenerar la firma sin el secret".

    El helper VIVE en `app/core/export_signatures.py` — NO en `routes.py`.
    Un test estático separado (`test_no_inline_hmac_signing_outside_signed_cookies_module`)
    bloquea HMAC inline en routes.py.
    """
    source = _source_of_export_signatures('sign_export_bundle')
    assert 'hmac.new(' in source, (
        'SEC-010-EXPORT-FU: la firma debe usar hmac.new — un hash plano '
        '(hashlib.sha256(content)) NO autentica.'
    )
    assert 'hashlib.sha256' in source, (
        'SEC-010-EXPORT-FU: la firma debe usar SHA256 — MD5/SHA1 son '
        'inaceptables para evidencia legal.'
    )
    assert 'settings.jwt_secret' in source, (
        'SEC-010-EXPORT-FU: el secret debe ser `settings.jwt_secret`. Hardcodear '
        'un secret literal o reutilizar uno débil revienta la integridad.'
    )
    assert '.hexdigest()' in source, (
        'SEC-010-EXPORT-FU: la firma debe ser hex-encoded — base64 con padding '
        'crea ambigüedades al pegarse en reportes.'
    )


def test_export_handler_does_not_inline_hmac():
    """Defensa de capas: el handler en routes.py debe DELEGAR a
    `sign_export_bundle`, no construir el HMAC inline. Sin esta guarda,
    alguien podría re-inlinearlo y violar el test
    `test_no_inline_hmac_signing_outside_signed_cookies_module`.
    """
    source = _source_of('export_contact_data')
    assert 'sign_export_bundle(' in source, (
        'SEC-010-EXPORT-FU: el handler debe llamar `sign_export_bundle(...)` '
        '— no construir hmac.new inline. Sin esto, el test global '
        '`test_no_inline_hmac_signing_outside_signed_cookies_module` falla.'
    )
    assert 'hmac.new(' not in source, (
        'SEC-010-EXPORT-FU: el handler NO debe contener hmac.new inline. '
        'Si necesitas variar la firma, extender app/core/export_signatures.py.'
    )


def test_handler_signs_canonical_json_not_raw_dict():
    """La firma debe ser sobre un JSON canónico (sorted_keys + no
    whitespace). Si alguien firma un dict directo o un JSON con orden
    arbitrario, dos exports del mismo bundle dan firmas distintas — el
    audit log queda inútil para verificación posterior.
    """
    source = _source_of('export_contact_data')
    assert 'sort_keys=True' in source, (
        'SEC-010-EXPORT-FU: el JSON canónico para firmar debe usar '
        'sort_keys=True — sin esto dos invocaciones idénticas producen '
        'firmas distintas y la auditoría no es verificable.'
    )
    assert "separators=(',', ':')" in source, (
        'SEC-010-EXPORT-FU: separators sin whitespace para que canonical '
        'JSON sea byte-exact reproducible.'
    )


def test_response_includes_signature_and_algorithm():
    """El response shape debe ser `{data, signature, signature_algorithm}` —
    el algoritmo explícito evita ambigüedad si en el futuro rotamos a otra
    primitiva (ej. blake2b, ed25519).
    """
    source = _source_of('export_contact_data')
    assert "'signature_algorithm': 'HMAC-SHA256'" in source, (
        'SEC-010-EXPORT-FU: el response debe declarar `signature_algorithm` '
        'literal para que el verificador no asuma.'
    )
    assert "'signature': signature" in source and "'data': bundle" in source, (
        'SEC-010-EXPORT-FU: el response shape es {data, signature, '
        'signature_algorithm}. Cambiar las keys rompe el contrato con el '
        'verificador documentado en el runbook.'
    )


# ───── Audit log ──────────────────────────────────────────────────────────


def test_handler_emits_audit_log_with_exact_action_name():
    """Action canónico: `contact.exported_for_consent_claim`. Cualquier
    typo o variante deja la auditoría rota — el dashboard de cumplimiento
    busca exactamente ese string.
    """
    source = _source_of('export_contact_data')
    assert "action='contact.exported_for_consent_claim'" in source, (
        'SEC-010-EXPORT-FU: el audit debe usar exactamente '
        "action='contact.exported_for_consent_claim' — cualquier variante "
        'rompe los dashboards de cumplimiento que filtran por ese string.'
    )
    assert "entity_type='contact'" in source, (
        'SEC-010-EXPORT-FU: entity_type debe ser `contact` para que el '
        'audit feed agrupe junto a las otras acciones contact-scoped.'
    )
    assert "entity_id=str(contact_id)" in source, (
        'SEC-010-EXPORT-FU: entity_id debe ser el contact_id (no el '
        'tenant_id) para identificar al sujeto del export en el feed.'
    )


def test_audit_metadata_includes_kinds_and_signature():
    """Metadata mínima necesaria para forensia: kinds (qué se exportó) +
    signature (hash de lo exportado, para verificar después que el archivo
    entregado no fue alterado) + exported_at (timestamp).
    """
    source = _source_of('export_contact_data')
    # El metadata es un dict literal pasado a audit(...). Busco las keys.
    assert "'kinds': list(requested_kinds)" in source, (
        'SEC-010-EXPORT-FU: el audit metadata debe incluir `kinds` para '
        'forensia (saber qué tipos de datos vieron al claimant).'
    )
    assert "'signature': signature" in source, (
        'SEC-010-EXPORT-FU: el audit metadata debe incluir la `signature` '
        'para poder re-verificar la integridad de un archivo exportado '
        'meses después.'
    )
    assert "'exported_at': bundle['exported_at']" in source, (
        'SEC-010-EXPORT-FU: el audit metadata debe incluir `exported_at` '
        'aunque audit_logs ya lleve created_at — el bundle timestamp es '
        'el que va FIRMADO y es el referenciado por la firma.'
    )
