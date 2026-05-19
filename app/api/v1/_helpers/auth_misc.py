"""Auth misc helpers extracted from app/api/v1/routes.py.

TASK-0077: per-tenant role ranking.  ``platform_owner`` is intentionally not
part of this table because that role is never stored in
``app.user_tenant_roles``; it lives in the JWT only.  The JWT half of the
double-check uses ``has_jwt_role`` from ``app.core.security`` which *does*
include ``platform_owner`` in its ranking.
BUG-133: `support` no es un rol — es un modo (`support_mode` flag/cookie).
Ver comment en `app/core/security.py::_ROLE_LEVELS` para la racional completa.
"""
from __future__ import annotations


_TENANT_ROLE_LEVELS = {
    'viewer': 5,
    'agent': 10,
    'manager': 20,
    'admin': 30,
    'owner': 40,
}


def _tenant_db_role_meets(role: str | None, minimum_role: str) -> bool:
    if role is None:
        return False
    return _TENANT_ROLE_LEVELS.get(role, 0) >= _TENANT_ROLE_LEVELS.get(minimum_role, 0)
