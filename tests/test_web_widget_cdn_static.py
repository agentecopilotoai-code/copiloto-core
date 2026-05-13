"""TASK-0070: static tests for the CDN-distributed embeddable web widget.

Covers:
- the new web-widget/ package layout (Vite build, eslint, scripts, tests)
- size-budget guardrails (≤ 30 KB gzip widget.js, ≤ 5 KB gzip widget.css)
- backend snippet builder now emits the CDN URL + new data-* attributes
- WebChannelUpsert schema accepts logo_url, welcome_copy, button_position
- admin panel exposes inputs for the new customisation fields
- the GitHub Action publishes to s3://copilotoia-cdn/widget/v1/
- the JS sources implement polling every 3s against GET messages
"""

from __future__ import annotations

from pathlib import Path

ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
WIDGET_DIR = Path('web-widget')
SRC = WIDGET_DIR / 'src'
TESTS = WIDGET_DIR / 'tests'
SCRIPTS = WIDGET_DIR / 'scripts'
WORKFLOW = Path('.github/workflows/web-widget.yml')
WEB_PANEL = Path('admin-panel/src/components/modules/whatsapp/WebWidgetPanel.jsx')


# ─────────────────────────────────────────────────────────────────────────────
# Package layout
# ─────────────────────────────────────────────────────────────────────────────


def test_web_widget_package_has_required_layout():
    assert WIDGET_DIR.is_dir()
    for path in [
        WIDGET_DIR / 'package.json',
        WIDGET_DIR / 'vite.config.js',
        WIDGET_DIR / 'eslint.config.js',
        WIDGET_DIR / 'README.md',
        SRC / 'main.js',
        SRC / 'widget.css',
        SRC / 'config.js',
        SRC / 'api.js',
        SRC / 'poller.js',
        SRC / 'ui.js',
        SRC / 'state.js',
        SCRIPTS / 'check-size.mjs',
    ]:
        assert path.is_file(), f'missing {path}'


def test_package_json_declares_build_lint_size_test_scripts():
    text = (WIDGET_DIR / 'package.json').read_text()
    for script in ('"build":', '"lint":', '"size":', '"test":', '"ci":'):
        assert script in text, f'package.json missing script {script}'
    # Vite + eslint + jsdom must be declared as devDependencies.
    assert '"vite":' in text
    assert '"eslint":' in text
    assert '"jsdom":' in text


def test_vite_config_emits_iife_widget_js_and_widget_css():
    text = (WIDGET_DIR / 'vite.config.js').read_text()
    # IIFE bundle (runs on any page), css extracted to widget.css.
    assert "format: 'iife'" in text
    assert "entryFileNames: 'widget.js'" in text
    assert "widget.css" in text
    # Single-file output: no code splitting, no dynamic chunks.
    assert 'cssCodeSplit: false' in text
    assert 'inlineDynamicImports: true' in text


# ─────────────────────────────────────────────────────────────────────────────
# Size budget
# ─────────────────────────────────────────────────────────────────────────────


def test_check_size_enforces_30kb_js_and_5kb_css_budget():
    text = (SCRIPTS / 'check-size.mjs').read_text()
    # Budgets per TASK-0070 acceptance criteria.
    assert "'dist/widget.js'" in text and 'maxGzipKb: 30' in text
    assert "'dist/widget.css'" in text and 'maxGzipKb: 5' in text
    assert 'gzipSync' in text
    assert 'process.exit(1)' in text


def test_widget_css_source_is_under_budget_uncompressed():
    # Sanity check on the un-minified source — minified+gzipped output is well
    # below this and is enforced by check-size.mjs in CI.
    css = (SRC / 'widget.css').read_text()
    assert len(css.encode('utf-8')) < 5 * 1024, 'widget.css source already > 5 KB raw'


def test_widget_src_total_is_under_30kb_uncompressed():
    total = sum(p.read_text().encode('utf-8').__len__() for p in SRC.glob('*.js'))
    # Minified + gzip cuts this by ~3-5x, so 90 KB of raw JS leaves comfortable
    # headroom for the 30 KB gzip budget.
    assert total < 90 * 1024, f'web-widget/src JS total {total} bytes too large'


# ─────────────────────────────────────────────────────────────────────────────
# Polling + customisation behaviour in JS sources
# ─────────────────────────────────────────────────────────────────────────────


def test_config_module_defines_three_second_poll_interval():
    text = (SRC / 'config.js').read_text()
    assert 'POLL_INTERVAL_MS = 3000' in text
    # Customisation surface: colour, greeting, logo, position, welcome copy.
    for attr in (
        "data-color",
        "data-greeting",
        "data-logo",
        "data-position",
        "data-welcome",
    ):
        assert attr in text


def test_api_module_targets_v1_web_chat_endpoints():
    text = (SRC / 'api.js').read_text()
    assert "/v1/web/chat/start" in text
    assert "/v1/web/chat/" in text
    assert "'/messages'" in text
    assert 'Bearer' in text  # session token forwarded for authed endpoints


def test_poller_dedupes_messages_and_calls_history():
    text = (SRC / 'poller.js').read_text()
    assert 'setInterval(tick' in text
    assert 'api.history(conversationId)' in text
    assert 'seen.has' in text  # dedupe by message id
    assert 'seen.add' in text


def test_main_entry_imports_css_and_arms_poller():
    text = (SRC / 'main.js').read_text()
    assert "import './widget.css'" in text
    assert 'createPoller' in text
    assert 'mountUi' in text


# ─────────────────────────────────────────────────────────────────────────────
# Tests directory in web-widget/ must hit the ≥ 6 acceptance criterion
# (lint, size, smoke) plus per-module unit coverage.
# ─────────────────────────────────────────────────────────────────────────────


def test_web_widget_has_at_least_six_test_cases():
    test_files = list(TESTS.glob('*.test.mjs'))
    assert test_files, 'web-widget/tests/ is empty'
    total = 0
    for path in test_files:
        text = path.read_text()
        total += text.count("test('") + text.count('test("')
    assert total >= 6, f'expected ≥ 6 test cases across web-widget/tests/, found {total}'


def test_web_widget_has_smoke_test_under_jsdom():
    smoke = TESTS / 'smoke.test.mjs'
    assert smoke.is_file()
    text = smoke.read_text()
    assert 'JSDOM' in text
    # The smoke test must boot mountUi and assert the chat panel renders.
    assert 'mountUi' in text
    assert 'cpi-fab' in text


# ─────────────────────────────────────────────────────────────────────────────
# Backend snippet builder + schemas
# ─────────────────────────────────────────────────────────────────────────────


def test_snippet_builder_points_at_cdn_and_emits_new_data_attrs():
    text = ROUTES.read_text()
    assert "WEB_WIDGET_CDN_URL = 'https://cdn.copilotoia.com/widget/v1/widget.js'" in text
    # New customisation surfaces on the snippet builder signature.
    assert 'logo_url: str | None = None' in text
    assert 'welcome_copy: str | None = None' in text
    assert 'button_position: str | None = None' in text
    # Data attribute names emitted in the snippet itself.
    assert 'data-logo=' in text
    assert 'data-welcome=' in text
    assert 'data-position=' in text


def test_build_widget_snippet_uses_cdn_and_all_attrs():
    # Direct call: validates we don't regress the attribute order or escaping.
    from app.api.v1.routes import _build_widget_snippet

    snippet = _build_widget_snippet(
        tenant_slug='demo-tenant',
        widget_token='wtok',
        color='#abcdef',
        greeting='Hola "amig@"',
        logo_url='https://cdn.example/logo.png',
        welcome_copy='Atendemos 24/7',
        button_position='left',
    )
    assert 'src="https://cdn.copilotoia.com/widget/v1/widget.js"' in snippet
    assert 'data-tenant="demo-tenant"' in snippet
    assert 'data-widget-token="wtok"' in snippet
    assert 'data-color="#abcdef"' in snippet
    # Greeting double-quotes must be HTML-escaped to keep the attribute valid.
    assert 'data-greeting="Hola &quot;amig@&quot;"' in snippet
    assert 'data-logo="https://cdn.example/logo.png"' in snippet
    assert 'data-welcome="Atendemos 24/7"' in snippet
    assert 'data-position="left"' in snippet


def test_build_widget_snippet_rejects_unknown_position():
    from app.api.v1.routes import _build_widget_snippet

    snippet = _build_widget_snippet(
        tenant_slug='demo',
        widget_token='tk',
        color=None,
        greeting=None,
        button_position='top-left',
    )
    assert 'data-position=' not in snippet


def test_web_channel_upsert_schema_accepts_new_fields():
    from app.api.v1.schemas import WebChannelUpsert

    payload = WebChannelUpsert(
        enabled=True,
        allowed_origins=['https://example.com'],
        primary_color='#1f7ae0',
        greeting='hello',
        logo_url='https://cdn.example/logo.png',
        welcome_copy='Atendemos 24/7',
        button_position='left',
    )
    assert payload.logo_url == 'https://cdn.example/logo.png'
    assert payload.welcome_copy == 'Atendemos 24/7'
    assert payload.button_position == 'left'


def test_web_channel_upsert_schema_rejects_invalid_button_position():
    import pytest
    from pydantic import ValidationError
    from app.api.v1.schemas import WebChannelUpsert

    with pytest.raises(ValidationError):
        WebChannelUpsert(button_position='top')


# ─────────────────────────────────────────────────────────────────────────────
# Admin panel inputs for the new customisation fields
# ─────────────────────────────────────────────────────────────────────────────


def test_web_widget_panel_renders_inputs_for_logo_welcome_and_position():
    text = WEB_PANEL.read_text()
    assert "'logo_url'" in text
    assert "'welcome_copy'" in text
    assert "'button_position'" in text
    # Render selectors for the new fields.
    assert 'Logo' in text
    assert 'Posición del botón' in text
    assert '<option value="left">' in text
    assert '<option value="right">' in text


# ─────────────────────────────────────────────────────────────────────────────
# GitHub Action — CDN publish
# ─────────────────────────────────────────────────────────────────────────────


def test_workflow_publishes_to_s3_copilotoia_cdn():
    assert WORKFLOW.is_file()
    text = WORKFLOW.read_text()
    assert 'web-widget' in text
    assert 'npm run build' in text
    assert 'npm run size' in text
    assert 'npm run lint' in text
    assert 'npm test' in text
    # Publishes both the mutable and immutable artefacts.
    assert 's3://copilotoia-cdn/widget/v1/widget.js' in text
    assert 's3://copilotoia-cdn/widget/v1/widget.css' in text
    assert 'widget.${{ github.sha }}.js' in text
    # OIDC-based AWS auth + CloudFront invalidation.
    assert 'aws-actions/configure-aws-credentials' in text
    assert 'create-invalidation' in text
