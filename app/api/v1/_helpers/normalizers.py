"""Normalizers transversales del core.

Solo contiene helpers que usan los handlers del core. Los módulos opt-in
que se instalen sobre el core declaran sus propios normalizers en su
feature folder.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


def _serialize_profile(prefs_row: asyncpg.Record, user_row: asyncpg.Record, user_id: UUID) -> dict[str, Any]:
    """Merge user_preferences (app cache) with app.users (Auth0-synced canonical fields)."""
    return {
        'user_id': str(user_id),
        'email': user_row['email'],
        # The cached display_name in user_preferences wins (the user explicitly
        # set it); fall back to the Auth0-synced one on app.users.
        'display_name': prefs_row['display_name'] or user_row['display_name'],
        'phone': prefs_row['phone'],
        'locale': prefs_row['locale'],
        'timezone': prefs_row['timezone'],
        'theme_override': prefs_row['theme_override'],
        'auth0_synced_at': (
            prefs_row['auth0_synced_at'].isoformat()
            if prefs_row['auth0_synced_at'] is not None
            else None
        ),
        'mfa_enabled': user_row['mfa_enabled'],
        'last_login_at': (
            user_row['last_login_at'].isoformat()
            if user_row['last_login_at'] is not None
            else None
        ),
    }
