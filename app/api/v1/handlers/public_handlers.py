"""Handlers extracted from routes.py for public_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api.v1._helpers.legal import html_escape_attr
from app.api.v1.routes import public_router
from app.db.pool import get_db
from app.services.legal import (
    LEGAL_KIND_LABELS_ES,
    LEGAL_KINDS,
    render_markdown_to_safe_html,
)


@public_router.get('/health')
async def health(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    await conn.fetchval('select 1')
    return {'status': 'ok'}


@public_router.get('/tenants/{tenant_id}/resources/public')
async def list_public_resources(
    tenant_id: UUID,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Expose public-facing specialist profiles for the web widget.

    Returns only resources flagged ``public_profile=true`` and ``is_active=true``.
    No auth: the widget snippet renders this client-side. Sensitive fields
    (capabilities, code, license) only surface when explicitly part of the
    public profile.
    """
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select r.id, r.name, r.specialty, r.bio, r.license_number,
               r.years_of_experience, r.photo_media_asset_id,
               m.source_uri as photo_url,
               m.mime_type as photo_mime_type
        from app.resources r
        left join app.media_assets m
          on m.id = r.photo_media_asset_id and m.tenant_id = r.tenant_id
        where r.tenant_id = $1
          and r.is_active = true
          and r.public_profile = true
        order by r.name asc
        limit 50
        """,
        tenant_id,
    )
    resources = []
    for row in rows:
        resources.append({
            'id': str(row['id']),
            'name': row['name'],
            'specialty': row['specialty'],
            'bio': row['bio'],
            'license_number': row['license_number'],
            'years_of_experience': row['years_of_experience'],
            'photo_url': row['photo_url'],
            'photo_mime_type': row['photo_mime_type'],
        })
    return {'resources': resources}


@public_router.get('/tenants/{tenant_id}/legal/{kind}')
async def get_public_legal_document(
    tenant_id: UUID,
    kind: str,
    language: str = Query(default='es', min_length=2, max_length=8),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Return the current published legal document as sanitized HTML.

    TASK-0076: required by Circular SIC 002 — anyone (including the data
    subject before signing up) must be able to read the privacy notice
    referenced from the consent template.  No auth: the page is public by
    contract; RLS is bypassed by ``set_config`` keyed on the path param.
    """
    if kind not in LEGAL_KINDS:
        raise HTTPException(status_code=404, detail='Unknown legal document kind')
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        select id, tenant_id, kind, language, version, title, content_md,
               published_at, archived_at, created_at
        from app.tenant_legal_documents
        where tenant_id=$1 and kind=$2 and language=$3
          and published_at is not null and archived_at is null
        limit 1
        """,
        tenant_id,
        kind,
        language,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Legal document not published')
    title = row['title']
    body_html = render_markdown_to_safe_html(row['content_md'])
    escaped_title = title.replace('<', '&lt;').replace('>', '&gt;')
    label = LEGAL_KIND_LABELS_ES.get(kind, kind)
    html_doc = (
        '<!doctype html><html lang="' + html_escape_attr(row['language']) + '"><head>'
        '<meta charset="utf-8">'
        '<meta name="robots" content="noindex">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{escaped_title} — {label} (v{row["version"]})</title>'
        '<style>body{font-family:system-ui,sans-serif;max-width:780px;margin:2rem auto;padding:0 1rem;line-height:1.55;color:#1f2937}'
        'article.legal-document h1,article.legal-document h2,article.legal-document h3{margin-top:1.4em}'
        'article.legal-document a{color:#2563eb}</style>'
        '</head><body>'
        f'<header><h1>{escaped_title}</h1>'
        f'<p><small>{label} — versión {row["version"]} — publicado {row["published_at"].date().isoformat()}</small></p></header>'
        f'{body_html}'
        '</body></html>'
    )
    return HTMLResponse(content=html_doc, status_code=200)
