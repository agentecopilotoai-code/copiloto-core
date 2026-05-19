"""Tenant secret reference helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import HTTPException


def tenant_secret_ref(tenant_id: UUID, secret_name: str) -> str:
    return f'secrets/tenants/{tenant_id}/{secret_name}'


def write_tenant_secret(secret_ref: str, value: str) -> None:
    relative_name = secret_ref.removeprefix('secrets/').strip('/')
    if not relative_name or '..' in Path(relative_name).parts:
        raise HTTPException(status_code=400, detail='Invalid tenant secret ref')
    path = Path('/app/.secrets') / relative_name
    if not path.parent.exists() and not Path('/app/.secrets').exists():
        path = Path.cwd() / '.secrets' / relative_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip(), encoding='utf-8')
    path.chmod(0o600)


def tenant_knowledge_s3_secret_ref(tenant_id: UUID) -> str:
    return tenant_secret_ref(tenant_id, 'knowledge_s3_secret_access_key')
