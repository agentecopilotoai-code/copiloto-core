"""Knowledge storage config helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.services.knowledge_storage import normalize_object_prefix
from app.services.whatsapp import secret_ref_is_configured


def default_knowledge_storage_config(tenant_id: UUID) -> dict[str, Any]:
    return {
        'backend': 'local',
        'bucket': None,
        'region': None,
        'endpoint_url': None,
        'prefix': f'tenants/{tenant_id}/knowledge',
        'access_key_id': None,
        'secret_ref': None,
    }


def normalize_knowledge_storage_config(tenant_id: UUID, value: Any) -> dict[str, Any]:
    config = default_knowledge_storage_config(tenant_id)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if isinstance(value, dict):
        for key in ('backend', 'bucket', 'region', 'endpoint_url', 'prefix', 'access_key_id', 'secret_ref'):
            if key in value:
                config[key] = value[key]
    config['backend'] = config.get('backend') if config.get('backend') in {'local', 's3'} else 'local'
    # Validate the prefix against traversal / root-like values. If the stored
    # config has a bad prefix (legacy data or a tenant admin that managed to
    # write '/' before this validation was in place), fall back to the
    # tenant-default rather than let an unrestricted prefix flow into the
    # deletion code path.
    try:
        config['prefix'] = normalize_object_prefix(config.get('prefix'), str(tenant_id))
    except ValueError:
        config['prefix'] = f'tenants/{tenant_id}/knowledge'
    return config


def public_knowledge_storage_config(tenant_id: UUID, config: dict[str, Any]) -> dict[str, Any]:
    response = normalize_knowledge_storage_config(tenant_id, config)
    response['secret_configured'] = secret_ref_is_configured(response.get('secret_ref'))
    response['effective_bucket'] = response.get('bucket') or get_settings().knowledge_storage_bucket
    return response
