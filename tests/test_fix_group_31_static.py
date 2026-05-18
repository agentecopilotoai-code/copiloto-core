"""Fix-group 31: BUG-174..BUG-178 — 4 P1 restantes + 1 P2 alto de Codex Review.

- BUG-174 (P1 sobre fix-group-11): test stale `default_locale` /
  `SUPPORTED_COUNTRIES`. NOT-APPLICABLE — el test fue renombrado y
  actualizado dentro del mismo PR de fix-group-11
  (`test_patch_my_profile_locale_validation_uses_canonical_set`).
- BUG-175 (P1 sobre BUG-079): `verify-backup.sh` skipeaba la validación
  de signer fingerprint cuando `BACKUP_SIGNER_FPR` estaba vacío → fall
  back a accept-any GOODSIG (trust-gap que BUG-079 cerraba). Fix:
  fail-closed con `report_failure backup_signer_fpr_unset` si la var
  está unset/empty.
- BUG-176 (P1 sobre BUG-047): `cpi_backup_last_verify_failed_age_seconds`
  era Gauge unlabeled → exportaba 0 por default desde import →
  `BackupVerifyFailed: max(...) < 86400` matcheaba 0 < 86400 = TRUE
  en greenfield. Fix: labeled Gauge `scope='cloud_verify'`; la serie
  queda absent hasta que se observa una failure real.
- BUG-177 (P1 sobre BUG-096): `TenantBrandLogo` usaba `<img src=
  proxyUrl>` pero el browser no manda `Authorization: Bearer ...` en
  `<img>` → 401. Fix: `fetchTenantMediaBlobUrl` en `coreApi.js` fetchea
  con auth headers, devuelve blob URL; `TenantBrandLogo` usa
  `useEffect` + cleanup. URLs externas (`https://cdn...`) siguen
  renderizadas directo (back-compat).
- BUG-178 (P2 sobre BUG-057): `BUG-057` se había marcado
  NOT-APPLICABLE-FOR-NOW porque "no había UI de web widget", pero el
  widget vive activo en `web-widget/src/api.js` +
  `admin-panel/public/widget.js`. `enforce_inbound_consent` para
  `opt_in='unknown'` ahora detecta `payload.channel='web'` y registra
  `granted` implícito en consent_ledger (el widget muestra el aviso
  upfront), dejando pasar al flow normal sin atascar al lead.
"""
from __future__ import annotations

from pathlib import Path


VERIFY_BACKUP = Path('scripts/verify-backup.sh')
METRICS = Path('app/services/metrics.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
TENANT_BRAND_LOGO = Path('admin-panel/src/app/shells/components/TenantBrandLogo.jsx')
SHELL_TOPBAR = Path('admin-panel/src/app/shells/components/ShellTopbar.jsx')
CONSENT = Path('app/services/consent.py')
USER_PREFS_TEST = Path('tests/test_user_preferences_static.py')


# ───── BUG-174 — NOT-APPLICABLE (test ya renombrado en fix-group-11) ─────


def test_bug_174_user_preferences_test_uses_canonical_assertion():
    src = USER_PREFS_TEST.read_text()
    # El test viejo está renombrado y ya defiende el patrón canonical.
    assert 'def test_patch_my_profile_locale_validation_uses_canonical_set' in src, (
        'BUG-174: el test debe estar renombrado al patrón canonical (en '
        'fix-group-11 lo cambiamos). Si vuelve a aparecer la versión vieja '
        '`uses_helper_not_values_call`, hay que re-flippear el assert.'
    )
    assert "'SUPPORTED_COUNTRIES.values()' not in source" in src
    assert "'SUPPORTED_USER_LOCALES' in source" in src


# ───── BUG-175 — verify-backup fail-closed cuando FPR vacío ──────────────


def test_bug_175_verify_backup_fails_closed_on_empty_signer_fpr():
    src = VERIFY_BACKUP.read_text()
    # Debe haber un guard explícito al inicio del bloque de validación de fpr.
    assert 'if [[ -z "${BACKUP_SIGNER_FPR:-}" ]]; then' in src, (
        'BUG-175: el script debe comprobar `-z BACKUP_SIGNER_FPR` y fail-closed '
        'ANTES del check de GOODSIG fingerprint. Sin esto, env var vacía → '
        'fall-back a accept-any-GOODSIG.'
    )
    assert 'backup_signer_fpr_unset' in src, (
        "BUG-175: el report_failure debe usar el reason `backup_signer_fpr_unset` "
        "para que el operador entienda que es un setup error, no un signature mismatch."
    )
    # Y NO debe quedar el viejo `if [[ -n "${BACKUP_SIGNER_FPR}" ]]` que skipeaba silentemente.
    # Defensa cruzada: la validación de FPR es ahora INCONDICIONAL (no envuelta en if-n).
    bug_079_block_start = src.find('# BUG-079: GOODSIG sólo dice')
    assert bug_079_block_start > 0
    next_block = src.find('echo "==> Descifrando con GPG', bug_079_block_start)
    block = src[bug_079_block_start:next_block]
    assert 'if [[ -n "${BACKUP_SIGNER_FPR:-}" ]]; then' not in block, (
        "BUG-175: el `if [[ -n ... ]]` viejo (que skipeaba la validación cuando "
        "la var estaba vacía) debe haberse removido — la validación ahora corre "
        "incondicionalmente tras el guard fail-closed."
    )


# ───── BUG-176 — gauge labeled para no exportar 0 default ────────────────


def test_bug_176_verify_failed_gauge_is_labeled():
    src = METRICS.read_text()
    gauge_idx = src.find('backup_last_verify_failed_age_seconds = Gauge(')
    assert gauge_idx > 0
    next_close = src.find(')\n', gauge_idx)
    block = src[gauge_idx:next_close]
    assert "labelnames=('scope',)" in block, (
        "BUG-176: el Gauge debe declarar `labelnames=('scope',)`. Unlabeled "
        "Gauges exportan 0 por default desde el import, lo que dispara "
        "`BackupVerifyFailed: max(...) < 86400` en greenfield."
    )


def test_bug_176_refresh_uses_label_when_setting_failed_age():
    src = METRICS.read_text()
    refresh_idx = src.find('async def refresh_backup_age_metrics(')
    assert refresh_idx > 0
    next_def = src.find('\n\n_VALID_DIRECTIONS', refresh_idx)
    block = src[refresh_idx:next_def]
    assert (
        "backup_last_verify_failed_age_seconds.labels(scope='cloud_verify').set("
        in block
    ), (
        "BUG-176: el setter debe usar `.labels(scope='cloud_verify').set(...)` "
        "para crear el child sólo cuando se observa una failure real. Sin esto, "
        "el cambio del Gauge a labeled no tiene efecto."
    )


# ───── BUG-177 — brand_logo blob fetch ───────────────────────────────────


def test_bug_177_core_api_exports_blob_fetch_helper():
    src = CORE_API.read_text()
    assert 'export async function fetchTenantMediaBlobUrl(' in src, (
        'BUG-177: `coreApi.js` debe exportar `fetchTenantMediaBlobUrl(session, '
        'tenantId, mediaPath)` para que componentes que rendereen media '
        'auth-protected puedan obtener un blob URL con auth headers.'
    )
    # El helper debe usar buildHeaders (Bearer + X-Tenant-Id).
    fn_idx = src.find('export async function fetchTenantMediaBlobUrl(')
    end = src.find('\n}\n', fn_idx)
    block = src[fn_idx:end]
    assert 'buildHeaders(session, tenantId,' in block, (
        'BUG-177: el helper debe usar `buildHeaders(session, tenantId, ...)` '
        'para incluir Bearer + X-Tenant-Id headers.'
    )
    assert 'URL.createObjectURL(blob)' in block, (
        'BUG-177: el helper debe devolver un object URL (`blob:`) que el '
        'caller asigne a `<img src>`.'
    )


def test_bug_177_tenant_brand_logo_uses_blob_fetch_for_internal_urls():
    src = TENANT_BRAND_LOGO.read_text()
    assert 'fetchTenantMediaBlobUrl' in src, (
        'BUG-177: el componente debe importar y usar `fetchTenantMediaBlobUrl` '
        'para los `brand_logo_url` internos (que requieren auth).'
    )
    # URLs externas (http/https) siguen renderizadas directo (back-compat).
    assert 'isExternalUrl' in src, (
        'BUG-177: debe existir un helper `isExternalUrl` que distinga URLs '
        'externas (http/https) del proxy interno; las externas no requieren '
        'auth y se rendean sin fetch.'
    )
    # Cleanup del blob URL al desmontar.
    assert 'URL.revokeObjectURL(blobUrl)' in src or 'URL.revokeObjectURL(' in src, (
        'BUG-177: el componente debe `URL.revokeObjectURL(...)` al desmontar '
        'para no leakar memoria.'
    )


def test_bug_177_shell_topbar_forwards_session_to_tenant_logo():
    src = SHELL_TOPBAR.read_text()
    assert 'session = null' in src or 'session,' in src, (
        'BUG-177: `ShellTopbar` debe aceptar `session` como prop.'
    )
    assert '<TenantBrandLogo session={session} tenant={tenant} />' in src, (
        'BUG-177: el `ShellTopbar` debe forwardear `session` al '
        '`TenantBrandLogo` para que pueda fetchear con auth.'
    )


# ───── BUG-178 — consent gate web channel ────────────────────────────────


def test_bug_179_operator_alerts_prebuilds_template_block():
    """BUG-179 (codex P1 sobre BUG-170): el event_worker espera el bloque
    `template` ya formateado bajo `payload['template']`. Si solo
    guardamos `template_name`/`template_locale`/`components` top-level,
    `message_payload.get('template')` devuelve None y
    `build_whatsapp_message_payload` raise ValueError → alert failed.
    """
    src = Path('app/services/operator_alerts.py').read_text()
    # Import del builder.
    assert 'from app.services.whatsapp import build_template_message_payload' in src, (
        "BUG-179: `operator_alerts.py` debe importar "
        "`build_template_message_payload` para pre-formatear el bloque "
        "template."
    )
    # Llamada al builder en `_send_whatsapp_channel`.
    fn_idx = src.find('async def _send_whatsapp_channel(')
    assert fn_idx > 0
    next_def = src.find('\nasync def _send_webhook_channel(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'template_block = build_template_message_payload(' in block, (
        "BUG-179: el helper debe construir `template_block` ANTES del "
        "loop por recipient para no repetir el trabajo."
    )
    # El payload del message insert lleva la key 'template' con el bloque.
    assert "'template': template_block" in block, (
        "BUG-179: el `app.messages.payload` debe incluir la key "
        "`'template'` con el bloque pre-construido. Sin esto, el "
        "event_worker pasa None a `build_whatsapp_message_payload` y "
        "raise ValueError."
    )


def test_bug_178_consent_gate_handles_web_channel_implicit_grant():
    src = CONSENT.read_text()
    # Buscar el bloque dedicado a web channel.
    web_idx = src.find("inbound_channel = inbound_payload_dict.get('channel')")
    assert web_idx > 0, (
        'BUG-178: el gate debe leer `payload.channel` del inbound para '
        'decidir si el lead viene del web widget.'
    )
    block = src[web_idx:src.find('# First-ever inbound from a brand-new contact', web_idx)]
    assert "if inbound_channel == 'web':" in block, (
        "BUG-178: la rama web debe disparar cuando `channel == 'web'`."
    )
    assert "channel='web'" in block, (
        "BUG-178: el `record_consent_event` debe usar `channel='web'` "
        "(no `whatsapp`) en el ledger entry."
    )
    assert "'source': 'web_widget_implicit_grant'" in block, (
        "BUG-178: la evidencia del ledger debe llevar "
        "`source='web_widget_implicit_grant'` para distinguir del flujo "
        "de botón WhatsApp."
    )
    # Debe setear opt_in_status='granted' (no 'revoked'/'suppressed').
    assert "set opt_in_status='granted'" in block, (
        'BUG-178: tras registrar el ledger event, debe actualizarse '
        '`contacts.opt_in_status=granted` para que el próximo inbound no '
        're-dispare el gate.'
    )
    # Y debe `return None` para que el orchestrator continúe (no es
    # short-circuit como el opt-out path).
    assert 'return None' in block, (
        'BUG-178: tras grant, debe `return None` para que el orquestador '
        'continúe con el flow normal (booking, RAG, etc.), no truncar como '
        'el opt-out path.'
    )
