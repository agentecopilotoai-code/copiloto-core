import asyncio
import json
from uuid import uuid4

from app.services.audit import audit


class FakeConnection:
    def __init__(self):
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))


def test_audit_serializes_default_metadata_for_jsonb():
    async def run_test():
        conn = FakeConnection()
        tenant_id = uuid4()

        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type='user',
            actor_id='auth0|user-1',
            action='tenant.self_service_created',
            entity_type='tenant',
            entity_id=str(tenant_id),
        )

        _, args = conn.calls[0]
        assert args[-1] == '{}'
        assert isinstance(args[-1], str)

    asyncio.run(run_test())


def test_audit_serializes_metadata_dict_for_jsonb():
    async def run_test():
        conn = FakeConnection()
        tenant_id = uuid4()

        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type='user',
            actor_id='auth0|user-1',
            action='tenant.updated',
            entity_type='tenant',
            entity_id=str(tenant_id),
            metadata={'source': 'admin-panel'},
        )

        _, args = conn.calls[0]
        assert json.loads(args[-1]) == {'source': 'admin-panel'}
        assert isinstance(args[-1], str)

    asyncio.run(run_test())
