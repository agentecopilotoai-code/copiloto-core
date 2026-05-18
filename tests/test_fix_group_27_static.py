"""Fix-group 27: BUG-153..BUG-157.

- BUG-153: VIGENTE. Para contacto `unknown` enviando STOP/BAJA, el
  consent gate corría ANTES del intent classifier y devolvía
  `consent_request_sent` → opt-out nunca corría y el usuario quedaba
  loopeado pidiéndole consent. Fix: detectar opt-out keywords en
  `enforce_inbound_consent` ANTES del branch `unknown` → send consent
  request, y registrar opt-out directo en el ledger.
- BUG-154: NOT-APPLICABLE. README ya aclara explícitamente que los
  workers de retención, alertas y extracción NO se incluyen en el
  compose por defecto (línea 1609); el lector debe arrancarlos manual.
- BUG-155: VIGENTE. `ServiceUpdate.recall_interval_days` aceptaba
  `ge=0`, pero el CHECK del schema es `null or > 0` → cliente puede
  mandar `0`, Pydantic lo acepta, INSERT/UPDATE rompe con 500. Fix:
  `gt=0` para alinear con `ServiceCreate` (línea 321).
- BUG-156: VIGENTE. El batch de anonimización de contacts en
  `retention.py` corría UNA sola vez con `limit 100`. Tenants con más
  de 100 contactos viejos quedaban semi-anonimizados. Fix: loop
  hasta que la batch devuelva menos filas que `page_size`.
- BUG-157: VIGENTE. `POST /v1/conversations/{id}/handoff` aceptaba
  `payload: dict` raw, sin validación de longitud. Aunque
  `normalize_handoff_reason` bucketea para Prometheus, el body raw
  permitía DOS con strings gigantes (en columna + memoria). Fix:
  nuevo `HandoffCreate` con `reason: str | None = Field(max_length=80)`.
"""
from __future__ import annotations

from pathlib import Path


CONSENT = Path('app/services/consent.py')
README = Path('README.md')
SCHEMAS = Path('app/api/v1/schemas.py')
RETENTION = Path('app/services/retention.py')
ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-153 — consent gate respeta opt-out de contactos unknown ──────


def test_bug_153_consent_module_imports_re_for_opt_out_detection():
    src = CONSENT.read_text()
    assert 'import re' in src, (
        "BUG-153: `consent.py` debe `import re` para compilar el patrón "
        "de opt-out keywords."
    )


def test_bug_153_consent_defines_opt_out_keyword_pattern():
    src = CONSENT.read_text()
    assert '_CONSENT_OPT_OUT_PATTERN = re.compile(' in src, (
        "BUG-153: debe existir `_CONSENT_OPT_OUT_PATTERN` (re.compile) "
        "con el subset de keywords de opt-out del intent_classifier "
        "(stop|baja|cancelar suscripción|...)."
    )
    # Las keywords clave deben estar.
    for kw in ('stop', 'baja', 'cancelar', 'd[ae]s?suscrib'):
        assert kw in src, (
            f"BUG-153: el patrón opt-out debe incluir `{kw}` (alineado con "
            "`intent_classifier._BASE_RULES`)."
        )


def test_bug_153_enforce_consent_short_circuits_opt_out_for_unknown():
    src = CONSENT.read_text()
    # El short-circuit debe correr ANTES del branch `if opt_in == 'unknown'`
    # que envía consent_request_sent. Buscamos la primera ocurrencia del
    # short-circuit y verificamos que está antes del branch obsoleto.
    short_circuit = "if _CONSENT_OPT_OUT_PATTERN.search(body_text_raw.lower())"
    unknown_branch = "First-ever inbound from a brand-new contact"
    assert short_circuit in src, (
        "BUG-153: `enforce_inbound_consent` debe chequear opt-out keywords "
        "antes de mandar el consent_request a contactos `unknown`."
    )
    sc_idx = src.find(short_circuit)
    ub_idx = src.find(unknown_branch)
    assert sc_idx > 0 and ub_idx > 0 and sc_idx < ub_idx, (
        "BUG-153: el short-circuit de opt-out debe estar ANTES del comentario "
        "'First-ever inbound from a brand-new contact'."
    )


def test_bug_153_opt_out_short_circuit_records_revoked_event():
    src = CONSENT.read_text()
    # Cuando matchea, debemos persistir un `revoked` event en consent_ledger
    # con source `opt_out_keyword_before_consent` para distinguirlo.
    assert "'opt_out_keyword_before_consent'" in src, (
        "BUG-153: el short-circuit debe registrar el evento `revoked` con "
        "`source='opt_out_keyword_before_consent'` para que el audit trail "
        "muestre que el opt-out llegó antes del consent."
    )
    assert "'opt_out_registered_before_consent'" in src, (
        "BUG-153: el ConsentDecision returned debe usar el reason "
        "`opt_out_registered_before_consent` para que el orquestador lo loguee."
    )


# ───── BUG-154 — README aclara que bootstrap no levanta workers extra ────


def test_bug_154_readme_disclaims_unincluded_workers():
    src = README.read_text()
    # El texto debe decir explícitamente que esos workers NO están en compose.
    assert (
        'retención, alertas y extracción no se incluyen en el compose' in src
    ), (
        "BUG-154: README debe aclarar que los workers de retención/alertas/"
        "extracción NO se incluyen en el compose por defecto. Sin esa nota, "
        "los usuarios asumen que `bootstrap.sh` los arranca."
    )


# ───── BUG-155 — ServiceUpdate.recall_interval_days alineado con DB ─────


def test_bug_155_service_update_recall_interval_days_uses_gt_0():
    src = SCHEMAS.read_text()
    update_idx = src.find('class ServiceUpdate(BaseModel)')
    assert update_idx > 0
    next_class = src.find('\nclass ', update_idx + 1)
    block = src[update_idx:next_class]
    assert 'recall_interval_days: int | None = Field(default=None, gt=0, le=3650)' in block, (
        "BUG-155: `ServiceUpdate.recall_interval_days` debe usar `gt=0`, "
        "no `ge=0`. El CHECK del schema es `null or > 0`, así que `0` "
        "pasa Pydantic y rompe con 500 al insertar/actualizar."
    )


# ───── BUG-156 — contacts anonymize batch loopea ─────────────────────────


def test_bug_156_retention_contacts_anonymize_uses_while_loop():
    src = RETENTION.read_text()
    # El bloque de contacts debe estar dentro de un while loop (igual que
    # messages/conversations), no ser un único execute con limit hardcodeado.
    contacts_idx = src.find(
        "After messages/conversations are anonymized, the contact's phone"
    )
    assert contacts_idx > 0
    # En el patrón nuevo el `while True:` aparece dentro del comentario fix.
    next_def = src.find('\n\nasync def ', contacts_idx)
    block = src[contacts_idx:next_def]
    assert 'while True:' in block, (
        "BUG-156: el batch de anonimización de contacts debe correr en un "
        "while loop hasta que la batch devuelva menos filas que `page_size` "
        "(igual que el patrón usado para messages/conversations)."
    )
    assert 'if n < page_size:' in block and 'break' in block, (
        "BUG-156: el loop debe terminar cuando `len(rows) < page_size` "
        "(señal de que ya no hay más contactos viejos por anonimizar)."
    )
    # Y no debe usar `100,` literal — debe usar `page_size`.
    assert 'page_size,' in block, (
        "BUG-156: el limit debe usar `page_size` (no hardcodeado)."
    )


# ───── BUG-157 — handoff endpoint usa Pydantic, no raw dict ──────────────


def test_bug_157_handoff_create_schema_exists_with_max_length():
    src = SCHEMAS.read_text()
    assert 'class HandoffCreate(BaseModel)' in src, (
        "BUG-157: debe existir un Pydantic model `HandoffCreate` para reemplazar "
        "el `payload: dict` raw del handoff endpoint."
    )
    hc_idx = src.find('class HandoffCreate(BaseModel)')
    next_class = src.find('\nclass ', hc_idx + 1)
    block = src[hc_idx:next_class]
    assert 'reason: str | None = Field(default=None, max_length=80)' in block, (
        "BUG-157: `HandoffCreate.reason` debe acotar `max_length=80` para "
        "evitar DOS con strings gigantes en body / columna."
    )


def test_bug_157_handoff_endpoint_uses_handoff_create_not_raw_dict():
    src = ROUTES.read_text()
    ep_idx = src.find(
        "@tenant_ops_router.post('/conversations/{conversation_id}/handoff', status_code=202)"
    )
    assert ep_idx > 0
    next_decl = src.find('\n@', ep_idx + 10)
    block = src[ep_idx:next_decl]
    assert 'payload: HandoffCreate' in block, (
        "BUG-157: el handoff endpoint debe usar `payload: HandoffCreate`, "
        "no `payload: dict` (raw)."
    )
    assert 'payload.reason' in block, (
        "BUG-157: el handler debe leer `payload.reason` (atributo Pydantic), "
        "no `payload.get('reason')` (dict raw)."
    )
