"""Fix-group 18: BUG-108..BUG-112.

- BUG-108: VIGENTE. `test_bot_personality_static._tenant_setup_source`
  usaba `rglob('*.js*')` que también incluye `.test.jsx` y `.test.js`,
  haciendo que los asserts pasen si la cadena vive en un test.
  Fix: filtrar paths con `.test.` en el nombre.
- BUG-109: VIGENTE. `useMediaLibraryData.pickFile` no limpiaba
  `uploadForm.file` cuando la validación fallaba → si el usuario había
  seleccionado un archivo válido antes y luego elige uno inválido, el
  archivo viejo quedaba en state y `upload()` lo enviaba.
  Fix: `setUploadForm({ ..., file: null, kind: '' })` en branch de error.
- BUG-110: VIGENTE. `KnowledgeStudio` montaba `useKnowledgeStudioData`
  antes del `<RequirePermission>` → fetch sin `knowledge.read` (403).
  Fix: split outer/Body.
- BUG-111: VIGENTE (cosmético/UX). Los FormField de secrets en
  `WhatsAppWizardSteps` tenían `required={!checks.X_configured}` solo
  en el `<input>` interior; el wrapper FormField no recibía `required`,
  así que el asterisco visual nunca aparecía. Fix: pasar `required` al
  FormField wrapper también para que la marca de obligatorio salga.
- BUG-112: VIGENTE. MRR del Platform Owner usaba `sp.price_amount`
  (precio actual del plan), no el precio "locked-in" del suscriptor →
  subir el precio del plan inflaba retroactivamente el MRR y la factura
  de los suscriptores existentes. Fix: nueva columna `price_locked_amount`
  + `price_locked_currency` en `contact_subscriptions`, snapshot en el
  subscribe, y queries usan `coalesce(cs.price_locked_amount, sp.price_amount)`.
"""
from __future__ import annotations

from pathlib import Path


BOT_PERSONALITY_TEST = Path('tests/test_bot_personality_static.py')
MEDIA_LIBRARY_HOOK = Path(
    'admin-panel/src/features/owner-admin/media-library/hooks/useMediaLibraryData.js'
)
KNOWLEDGE_STUDIO = Path(
    'admin-panel/src/features/owner-admin/knowledge-studio/KnowledgeStudio.jsx'
)
WHATSAPP_WIZARD_STEPS = Path(
    'admin-panel/src/features/owner-admin/whatsapp/components/WhatsAppWizardSteps.jsx'
)
SCHEMA = Path('infra/postgres/01-schema.sql')
MIGRATIONS = Path('infra/postgres/03-migrations.sql')
ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-108 — rglob excluye tests ─────────────────────────────────────


def test_bug_108_bot_personality_test_excludes_test_files_from_rglob():
    src = BOT_PERSONALITY_TEST.read_text()
    assert "'.test.' not in p.name" in src, (
        "BUG-108: `_tenant_setup_source` debe filtrar `*.test.js*` para que los "
        "asserts no pasen porque la cadena viva en un test (en vez de en código de prod)."
    )


# ───── BUG-109 — pickFile limpia file en validation failure ──────────────


def test_bug_109_pick_file_clears_stale_file_on_validation_error():
    src = MEDIA_LIBRARY_HOOK.read_text()
    # En el branch del error, debemos limpiar `file: null` y `kind: ''`.
    pick_idx = src.find('pickFile:')
    assert pick_idx > 0
    # Buscar el bloque hasta el siguiente action (openCreatePromo).
    next_idx = src.find('openCreatePromo:', pick_idx)
    block = src[pick_idx:next_idx]
    assert "setNotice({ type: 'error', text: error });" in block
    assert 'file: null' in block.split('error })')[-1] or 'file: null' in block, (
        'BUG-109: pickFile debe limpiar `file` en validation failure.'
    )
    # Aserción más estricta: la limpieza ocurre DESPUÉS de setNotice del error.
    after_setnotice = block.split("setNotice({ type: 'error', text: error });", 1)[1]
    assert 'file: null' in after_setnotice and "kind: ''" in after_setnotice, (
        'BUG-109: tras `setNotice(error)`, pickFile debe hacer '
        "`setUploadForm((prev) => ({ ...prev, file: null, kind: '' }))`."
    )


# ───── BUG-110 — KnowledgeStudio split outer/Body ────────────────────────


def test_bug_110_knowledge_studio_gates_before_data_hook():
    src = KNOWLEDGE_STUDIO.read_text()
    assert 'KnowledgeStudioBody' in src, (
        'BUG-110: el split debe introducir `KnowledgeStudioBody`.'
    )
    outer_idx = src.find('export function KnowledgeStudio(props)')
    body_idx = src.find('function KnowledgeStudioBody(')
    assert outer_idx >= 0 and body_idx > outer_idx
    outer_block = src[outer_idx:body_idx]
    assert 'useKnowledgeStudioData' not in outer_block, (
        'BUG-110: el outer NO debe invocar `useKnowledgeStudioData` antes del gate.'
    )
    assert '<RequirePermission' in outer_block
    assert 'capability="knowledge.read"' in outer_block


# ───── BUG-111 — WhatsApp wizard FormField required propagation ──────────


def test_bug_111_whatsapp_secret_form_fields_pass_required_to_wrapper():
    src = WHATSAPP_WIZARD_STEPS.read_text()
    # Los tres campos secret deben tener `required={!checks.X_configured}` en
    # el FormField wrapper, no solo en el input interior.
    for prop in (
        'required={!checks.meta_access_token_configured}',
        'required={!checks.app_secret_configured}',
        'required={!checks.verify_token_configured}',
    ):
        # Aparece ≥ 2 veces: una en FormField wrapper, otra en el <input> interior.
        assert src.count(prop) >= 2, (
            f'BUG-111: `{prop}` debe estar tanto en el FormField wrapper como '
            'en el <input> interior para que el asterisco visual aparezca.'
        )


# ───── BUG-112 — MRR usa precio locked-in del suscriptor ─────────────────


def test_bug_112_schema_has_price_locked_columns():
    src = SCHEMA.read_text()
    cs_idx = src.find('create table app.contact_subscriptions (')
    assert cs_idx > 0
    cs_end = src.find(');', cs_idx)
    cs_block = src[cs_idx:cs_end]
    assert 'price_locked_amount numeric' in cs_block, (
        'BUG-112: `contact_subscriptions.price_locked_amount` falta — sin esto '
        'el MRR sigue dependiente del precio actual del plan.'
    )
    assert 'price_locked_currency text' in cs_block, (
        'BUG-112: `contact_subscriptions.price_locked_currency` falta — '
        'necesitamos snapshot del currency junto al amount.'
    )


def test_bug_112_migrations_add_price_locked_columns_idempotently():
    src = MIGRATIONS.read_text()
    assert 'add column if not exists price_locked_amount numeric' in src, (
        'BUG-112: migración idempotente de `price_locked_amount` falta — '
        'instalaciones existentes no obtendrían la columna.'
    )
    assert 'add column if not exists price_locked_currency text' in src, (
        'BUG-112: migración idempotente de `price_locked_currency` falta.'
    )


def test_bug_112_mrr_queries_use_coalesce_locked_price():
    src = ROUTES.read_text()
    # Las 3 queries del MRR endpoint deben usar coalesce(cs.price_locked_amount, sp.price_amount).
    mrr_idx = src.find("@platform_admin_router.get('/platform/billing/mrr')")
    assert mrr_idx > 0
    next_route_idx = src.find('@platform_admin_router', mrr_idx + 10)
    mrr_block = src[mrr_idx:next_route_idx]
    occurrences = mrr_block.count('coalesce(cs.price_locked_amount, sp.price_amount)')
    assert occurrences >= 4, (
        'BUG-112: las 4 queries del endpoint MRR (tenant/plan/country/failed) '
        'deben usar `coalesce(cs.price_locked_amount, sp.price_amount)` para que '
        'subir el precio del plan no altere retroactivamente el MRR de los '
        f'suscriptores existentes. Hallé {occurrences} usos.'
    )


def test_bug_112_create_contact_subscription_snapshots_plan_price():
    src = ROUTES.read_text()
    create_idx = src.find('async def create_contact_subscription(')
    assert create_idx > 0
    next_def = src.find('\nasync def ', create_idx + 1)
    block = src[create_idx:next_def]
    # El SELECT del plan debe traer price_amount + currency (para snapshotear).
    assert 'select id, price_amount, currency from app.subscription_plans' in block, (
        'BUG-112: el SELECT del plan en `create_contact_subscription` debe '
        'incluir `price_amount` + `currency` para snapshotearlos en el subscribe.'
    )
    # El INSERT debe escribir price_locked_amount y price_locked_currency.
    assert 'price_locked_amount, price_locked_currency' in block, (
        'BUG-112: el INSERT debe incluir las columnas `price_locked_amount` '
        '+ `price_locked_currency`.'
    )
    assert "plan['price_amount']" in block, (
        'BUG-112: el valor de `price_locked_amount` debe venir del plan en el '
        'momento del subscribe.'
    )
