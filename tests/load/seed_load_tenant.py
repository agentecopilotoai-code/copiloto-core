"""TASK-0072 — Seed a load-test tenant + WhatsApp channel.

Run once against the target stack before invoking Locust::

    python -m tests.load.seed_load_tenant

The script is idempotent: if the tenant already exists, it is reused. The
generated IDs (tenant_id, phone_number_id) and the HMAC app_secret are written
to `.secrets/load_test_*` so the Locust file picks them up automatically.

Environment::

    DATABASE_URL                postgres URL with create privileges on `app.*`
    LOAD_TEST_SLUG              optional slug (default `load-test`)
"""
from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECRETS_DIR = REPO_ROOT / '.secrets'


def _database_url() -> str:
    url = os.getenv('DATABASE_URL') or os.getenv('TEST_DATABASE_URL')
    if not url:
        raise SystemExit('DATABASE_URL must be set for the seed step')
    return url


def _write_secret(name: str, value: str) -> Path:
    SECRETS_DIR.mkdir(exist_ok=True)
    path = SECRETS_DIR / name
    path.write_text(value, encoding='utf-8')
    path.chmod(0o600)
    return path


async def seed() -> dict[str, str]:
    import asyncpg

    slug = os.getenv('LOAD_TEST_SLUG', 'load-test')
    phone_number_id = f'pn-{slug}'
    app_secret = secrets.token_hex(32)

    conn = await asyncpg.connect(_database_url())
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")

        existing = await conn.fetchrow(
            'select id from app.tenants where slug=$1', slug,
        )
        if existing:
            tenant_id = existing['id']
        else:
            tenant_id = uuid.uuid4()
            await conn.execute(
                """
                insert into app.tenants
                  (id, slug, legal_name, display_name, vertical_code,
                   country_code, timezone, status)
                values ($1, $2, 'Load Test Tenant', 'Load Test',
                        'general', 'CO', 'America/Bogota', 'active')
                """,
                tenant_id,
                slug,
            )
            await conn.execute(
                """
                insert into app.tenant_settings (tenant_id, escalation_policy)
                values ($1,
                        '{"triggers": {"keywords": ["humano"], "after_bot_turns": 5}}'::jsonb)
                """,
                tenant_id,
            )

        await conn.execute(
            "select set_config('app.tenant_id', $1, false)", str(tenant_id),
        )

        # Write the app secret to disk first so `resolve_secret_ref` picks it
        # up before we point the channel at it.
        _write_secret('load_test_app_secret', app_secret)
        secret_ref = 'secrets/load_test_app_secret'

        existing_channel = await conn.fetchrow(
            """
            select id from app.tenant_channels
            where tenant_id=$1 and provider='whatsapp_cloud_api'
            """,
            tenant_id,
        )
        if existing_channel:
            await conn.execute(
                """
                update app.tenant_channels
                   set phone_number_id=$2, app_secret_ref=$3, status='active',
                       account_mode='mock'
                 where id=$1
                """,
                existing_channel['id'],
                phone_number_id,
                secret_ref,
            )
        else:
            await conn.execute(
                """
                insert into app.tenant_channels
                  (tenant_id, provider, phone_number_id, token_ref,
                   app_secret_ref, account_mode, status)
                values ($1, 'whatsapp_cloud_api', $2,
                        'secrets/load_test_token', $3, 'mock', 'active')
                """,
                tenant_id,
                phone_number_id,
                secret_ref,
            )
    finally:
        await conn.close()

    _write_secret('load_test_tenant_id', str(tenant_id))
    _write_secret('load_test_phone_number_id', phone_number_id)

    return {
        'tenant_id': str(tenant_id),
        'phone_number_id': phone_number_id,
        'app_secret': app_secret,
    }


def main() -> None:
    result = asyncio.run(seed())
    print('Load tenant ready:')
    for key, value in result.items():
        display = value if key != 'app_secret' else f'{value[:8]}…'
        print(f'  {key:18s} = {display}')


if __name__ == '__main__':
    main()
