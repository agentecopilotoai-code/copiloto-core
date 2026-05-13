"""TASK-0072 — Locust load suite (mixed journey profile).

Run with::

    locust -f tests/load/test_journey_load.py \\
           --host http://localhost:8000 \\
           --headless --users 50 --spawn-rate 10 \\
           --run-time 5m --csv tests/load/results/run

The `tests/load/seed_load_tenant.py` script must have run first against the
target stack so that the load tenant + WhatsApp channel exist with a known
`app_secret`. The same secret is read here from the env var
`LOAD_TEST_APP_SECRET` (or from `.secrets/load_test_app_secret`).

Traffic mix (`@task` weights are 7/2/1):

  * 70%  WhatsApp inbound webhook (signed HMAC, full RAG path)
  * 20%  Panel-style read queries (health + public resources)
  * 10%  Admin/catalog read queries via the service token

SLA target (see ``docs/sla.md``): p95 < 2s @ 50 msg/s sustained for 5 min.
The acceptance criterion is asserted by ``tests/load/aggregate_results.py``
when run with ``--enforce-sla``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

try:  # Locust is a load-test only dep; tolerate absence in unit-test CI.
    from locust import HttpUser, between, events, task
except ImportError:  # pragma: no cover - exercised only without locust installed
    HttpUser = object  # type: ignore[assignment,misc]

    def task(weight=1):  # type: ignore[no-redef]
        def _wrap(fn):
            fn._locust_task_weight = weight
            return fn

        return _wrap

    def between(_a, _b):  # type: ignore[no-redef]
        return None

    class _NoopEvents:
        def __getattr__(self, _name):
            class _Hook:
                def add_listener(self, *_a, **_kw):
                    return None

            return _Hook()

    events = _NoopEvents()  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SECRET_FILENAME = 'load_test_app_secret'


def _load_app_secret() -> str:
    env = os.getenv('LOAD_TEST_APP_SECRET', '').strip()
    if env:
        return env
    for path in (
        REPO_ROOT / '.secrets' / SECRET_FILENAME,
        Path('/app/.secrets') / SECRET_FILENAME,
    ):
        if path.is_file():
            return path.read_text(encoding='utf-8').strip()
    # No secret available: tests will still issue requests, but signature
    # verification on the server side will reject them. This keeps the suite
    # runnable in smoke-only mode.
    return 'change-me-load-test'


def _load_tenant_id() -> str:
    """The seed script writes the tenant_id to .secrets/load_test_tenant_id."""
    env = os.getenv('LOAD_TEST_TENANT_ID', '').strip()
    if env:
        return env
    for path in (
        REPO_ROOT / '.secrets' / 'load_test_tenant_id',
        Path('/app/.secrets') / 'load_test_tenant_id',
    ):
        if path.is_file():
            return path.read_text(encoding='utf-8').strip()
    return '00000000-0000-0000-0000-000000000000'


def _load_phone_number_id() -> str:
    env = os.getenv('LOAD_TEST_PHONE_NUMBER_ID', '').strip()
    if env:
        return env
    for path in (
        REPO_ROOT / '.secrets' / 'load_test_phone_number_id',
        Path('/app/.secrets') / 'load_test_phone_number_id',
    ):
        if path.is_file():
            return path.read_text(encoding='utf-8').strip()
    return 'pn-load-test'


def _service_token() -> str:
    env = os.getenv('SERVICE_TOKEN', '').strip()
    if env:
        return env
    for path in (
        REPO_ROOT / '.secrets' / 'service_token',
        Path('/app/.secrets') / 'service_token',
    ):
        if path.is_file():
            return path.read_text(encoding='utf-8').strip()
    return ''


APP_SECRET = _load_app_secret()
TENANT_ID = _load_tenant_id()
PHONE_NUMBER_ID = _load_phone_number_id()
SERVICE_TOKEN = _service_token()


def _sign(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return f'sha256={digest}'


def _build_inbound_payload(wa_id: str, text: str) -> dict:
    """Build a minimal WhatsApp Cloud API inbound payload.

    The orchestrator only requires phone_number_id + a `messages[]` entry of
    type `text`. We keep the wa_id stable per virtual user so the contact
    cache + retrieval cache warm up over the test window.
    """
    return {
        'object': 'whatsapp_business_account',
        'entry': [
            {
                'id': 'load-test',
                'changes': [
                    {
                        'value': {
                            'messaging_product': 'whatsapp',
                            'metadata': {'phone_number_id': PHONE_NUMBER_ID},
                            'contacts': [
                                {'wa_id': wa_id, 'profile': {'name': 'Load Tester'}},
                            ],
                            'messages': [
                                {
                                    'id': f'wamid.{uuid.uuid4().hex}',
                                    'from': wa_id,
                                    'timestamp': str(int(time.time())),
                                    'type': 'text',
                                    'text': {'body': text},
                                },
                            ],
                        },
                        'field': 'messages',
                    },
                ],
            },
        ],
    }


# Pool of phrases that exercise different intent branches (FAQ, booking,
# escalation). Mixed input prevents the suite from being a single-flow probe.
PROMPTS = [
    '¿Cuánto cuesta un corte de cabello?',
    'Quiero agendar una cita para mañana en la tarde',
    'Necesito hablar con un humano por favor',
    '¿Qué servicios ofrecen?',
    'Hola, buenos días',
    'Cancelar mi cita',
    '¿Tienen disponibilidad el viernes?',
    'Gracias!',
]


class JourneyUser(HttpUser):
    """Virtual user that mimics a tenant's mixed traffic profile."""

    # 1–3 s think time keeps a single user under 1 RPS; with 50 concurrent
    # users this lands around 25–50 RPS, matching the SLA target.
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.wa_id = f'57300{int(uuid.uuid4().int % 10_000_000):07d}'
        self.prompt_idx = 0

    # ─── 70% — WhatsApp inbound webhook ────────────────────────────────────
    @task(7)
    def inbound_message(self) -> None:
        prompt = PROMPTS[self.prompt_idx % len(PROMPTS)]
        self.prompt_idx += 1
        payload = _build_inbound_payload(self.wa_id, prompt)
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Signature-256': _sign(body),
        }
        with self.client.post(
            '/v1/webhooks/whatsapp',
            data=body,
            headers=headers,
            name='POST /v1/webhooks/whatsapp',
            catch_response=True,
        ) as resp:
            # 202 = accepted, 200 = also fine if the platform decides to ACK.
            # 401/404 mean the seed script never ran — fail loudly.
            if resp.status_code in (200, 202):
                resp.success()
            else:
                resp.failure(f'unexpected status {resp.status_code}: {resp.text[:120]}')

    # ─── 20% — panel-style read queries ────────────────────────────────────
    @task(2)
    def panel_reads(self) -> None:
        # Health hit is the cheapest panel probe; the public resources query
        # touches RLS-bound SELECTs so it stresses the connection pool too.
        with self.client.get('/v1/health', name='GET /v1/health', catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f'health degraded: {r.status_code}')
        if TENANT_ID and TENANT_ID != '00000000-0000-0000-0000-000000000000':
            self.client.get(
                f'/v1/tenants/{TENANT_ID}/resources/public',
                name='GET /v1/tenants/[tid]/resources/public',
            )

    # ─── 10% — admin / catalog reads via service token ────────────────────
    @task(1)
    def admin_actions(self) -> None:
        if not SERVICE_TOKEN or not TENANT_ID:
            return
        headers = {
            'Authorization': f'Bearer {SERVICE_TOKEN}',
            'X-Tenant-Id': TENANT_ID,
        }
        # `tenant_catalog_router` allows service tokens; this exercises a
        # representative authenticated read path through the policy engine.
        self.client.get(
            f'/v1/tenants/{TENANT_ID}/services',
            headers=headers,
            name='GET /v1/tenants/[tid]/services',
        )


# ── Locust runtime hooks ─────────────────────────────────────────────────────
@events.test_start.add_listener
def _on_test_start(environment, **_kwargs):  # pragma: no cover - runtime hook
    if APP_SECRET == 'change-me-load-test':
        print(
            'WARNING: LOAD_TEST_APP_SECRET / .secrets/load_test_app_secret not set. '
            'Inbound webhook requests will be rejected by signature verification.',
        )


@events.quitting.add_listener
def _on_quit(environment, **_kwargs):  # pragma: no cover - runtime hook
    """Enforce SLA at the process exit.

    The job CI wraps this with ``aggregate_results.py --enforce-sla`` for the
    canonical check; this is a fast-fail hook for local runs.
    """
    stats = environment.stats.total
    p95 = stats.get_response_time_percentile(0.95)
    rps = stats.total_rps
    target_p95_ms = float(os.getenv('LOAD_TEST_P95_MS', '2000'))
    target_rps = float(os.getenv('LOAD_TEST_RPS', '25'))
    if rps < target_rps:
        print(f'SLA WARN: sustained RPS {rps:.1f} below target {target_rps}')
    if p95 and p95 > target_p95_ms:
        print(f'SLA FAIL: p95 {p95:.0f}ms above target {target_p95_ms:.0f}ms')
        environment.process_exit_code = 1
