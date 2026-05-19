"""Web widget snippet builder extracted from app/api/v1/routes.py."""
from __future__ import annotations

from app.core import config as core_config


def _build_widget_snippet(
    *,
    tenant_slug: str,
    widget_token: str,
    color: str | None,
    greeting: str | None,
    logo_url: str | None = None,
    welcome_copy: str | None = None,
    button_position: str | None = None,
) -> str:
    # TASK-0070: snippet points at the CDN-hosted bundle and carries the full
    # per-tenant customisation as data-* attributes so the widget renders
    # without an extra round-trip. ``data-api-base`` is required: the CDN host
    # only serves static assets, so the widget must know the real API origin
    # to call /v1/web/chat/*.
    settings = core_config.get_settings()
    attrs = [
        f'src="{settings.web_widget_cdn_url}"',
        f'data-tenant="{tenant_slug}"',
        f'data-widget-token="{widget_token}"',
        f'data-api-base="{settings.web_widget_api_base.rstrip("/")}"',
    ]
    if color:
        attrs.append(f'data-color="{color}"')
    if greeting:
        safe = greeting.replace('"', '&quot;')
        attrs.append(f'data-greeting="{safe}"')
    if logo_url:
        # BUG-226 (codex MEDIUM, 2026-05-18): el `greeting` y `welcome_copy`
        # arriba escapan `"` a `&quot;`, pero `logo_url` se insertaba RAW.
        # Tenant admin podía persistir `logo_url=x" onload="alert(...)`,
        # el snippet generado terminaba con un `<script>` con un onload
        # handler atacante en el origin del tenant site. Cualquier visitor
        # del site que ejecute el snippet oficial corría el JS del atacante.
        safe_logo = logo_url.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        attrs.append(f'data-logo="{safe_logo}"')
    if welcome_copy:
        safe = welcome_copy.replace('"', '&quot;')
        attrs.append(f'data-welcome="{safe}"')
    if button_position in ('left', 'right'):
        attrs.append(f'data-position="{button_position}"')
    return '<script async ' + ' '.join(attrs) + '></script>'
