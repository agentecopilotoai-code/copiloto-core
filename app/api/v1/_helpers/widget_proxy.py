"""Helpers for tenant-scoped widget/media proxy URLs."""
from __future__ import annotations

from uuid import UUID


# BUG-096: helper para construir la URL canónica del proxy de media
# tenant-scoped. Mantener sincronizado con la ruta del endpoint
# `get_tenant_media_content` declarado abajo.
def tenant_brand_logo_proxy_url(tenant_id: UUID, asset_id: UUID) -> str:
    return f'/v1/tenants/{tenant_id}/media/{asset_id}/content'
