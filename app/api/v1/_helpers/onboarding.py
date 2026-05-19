"""Onboarding pure helpers + constants extracted from app/api/v1/routes.py.

TASK-0069 — Wizard de onboarding self-service con verificación paso-a-paso.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


ONBOARDING_TOTAL_STEPS = 7
ONBOARDING_STEPS = tuple(range(1, ONBOARDING_TOTAL_STEPS + 1))
ONBOARDING_STEP_METADATA = {
    1: {'key': 'business_details', 'label': 'Datos del negocio'},
    2: {'key': 'locale_currency', 'label': 'Timezone, locale y moneda'},
    3: {'key': 'whatsapp_channel', 'label': 'Canal WhatsApp con firma verificada'},
    4: {'key': 'consent_template', 'label': 'Template consent_request_v1'},
    5: {'key': 'service_catalog', 'label': 'Catálogo de servicios mínimo'},
    6: {'key': 'business_hours', 'label': 'Horarios de atención'},
    7: {'key': 'end_to_end_test', 'label': 'Test E2E del bot'},
}
ONBOARDING_CONSENT_TEMPLATE_NAME = 'consent_request_v1'


def normalize_onboarding_progress(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    try:
        last_completed = int(data.get('last_completed_step') or 0)
    except (TypeError, ValueError):
        last_completed = 0
    last_completed = max(0, min(last_completed, ONBOARDING_TOTAL_STEPS))
    steps_raw = data.get('steps') if isinstance(data.get('steps'), dict) else {}
    steps: dict[str, Any] = {}
    for n in ONBOARDING_STEPS:
        entry = steps_raw.get(str(n)) if isinstance(steps_raw, dict) else None
        if isinstance(entry, dict):
            steps[str(n)] = entry
    return {
        'step': min(last_completed + 1, ONBOARDING_TOTAL_STEPS),
        'total': ONBOARDING_TOTAL_STEPS,
        'last_completed_step': last_completed,
        'steps': steps,
        'complete': last_completed >= ONBOARDING_TOTAL_STEPS,
    }


def _step_metadata(step: int) -> dict[str, Any]:
    meta = ONBOARDING_STEP_METADATA.get(step)
    if not meta:
        raise HTTPException(status_code=400, detail=f'Step {step} inválido (1..{ONBOARDING_TOTAL_STEPS}).')
    return meta
