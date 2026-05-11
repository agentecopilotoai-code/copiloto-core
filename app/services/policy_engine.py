"""Policy engine for centralized bot behavior and handoff decisions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class PolicyResult:
    action: Literal['continue_bot', 'require_handoff', 'block']
    reason: str
    risk_level: Literal['low', 'medium', 'high']


def evaluate_policy(
    tenant_settings: dict[str, Any],
    conversation: dict[str, Any],
    message_text: str,
    intent: str,
) -> PolicyResult:
    """Evaluate conversation policies in priority order.

    Rules evaluated (highest to lowest priority):
    1. Intent complaint_or_risk → require_handoff immediately (risk_level=high).
    2. Risk keywords in escalation_policy.risk_keywords → require_handoff (risk_level=high).
    3. Service window expired (when enforce_service_window is true) → require_handoff (risk_level=medium).
    4. Bot turns >= max_bot_turns → require_handoff (risk_level=medium).
    5. Consecutive no-context responses >= limit → require_handoff (risk_level=medium).

    The ``conversation`` dict must contain:
    - ``bot_turn_count`` (int): outbound bot messages in this conversation.
    - ``consecutive_no_context`` (int): consecutive recent bot responses without sufficient context.
    - ``service_window_expires_at`` (datetime | str | None): WhatsApp 24 h service window expiry.

    The ``tenant_settings`` dict must contain:
    - ``max_bot_turns`` (int): maximum bot turns before escalation.
    - ``escalation_policy`` (dict | str): jsonb escalation policy with optional fields:
      - ``risk_keywords`` (list[str]): additional risk keywords triggering handoff.
      - ``enforce_service_window`` (bool, default True): whether to enforce the 24 h window.
      - ``consecutive_no_context_limit`` (int, default 2): consecutive no-context threshold.
    """
    escalation_policy = _parse_json(tenant_settings.get('escalation_policy') or {})
    max_bot_turns = _to_positive_int(tenant_settings.get('max_bot_turns'), default=8)
    consecutive_no_context_limit = _to_positive_int(
        escalation_policy.get('consecutive_no_context_limit'), default=2
    )

    # Rule 1: complaint_or_risk intent forces immediate handoff.
    if intent == 'complaint_or_risk':
        return PolicyResult(
            action='require_handoff',
            reason='intent_complaint_or_risk',
            risk_level='high',
        )

    # Rule 2: risk keywords from escalation_policy.risk_keywords.
    risk_keywords: list = escalation_policy.get('risk_keywords') or []
    message_lower = message_text.lower()
    triggered = next(
        (
            kw.strip().lower()
            for kw in risk_keywords
            if isinstance(kw, str) and kw.strip() and kw.strip().lower() in message_lower
        ),
        None,
    )
    if triggered:
        return PolicyResult(
            action='require_handoff',
            reason=f'risk_keyword:{triggered}',
            risk_level='high',
        )

    # Rule 3: WhatsApp service window expired (only when enforcement is enabled).
    enforce_window = escalation_policy.get('enforce_service_window', True)
    if enforce_window:
        expires_at = _parse_datetime(conversation.get('service_window_expires_at'))
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                return PolicyResult(
                    action='require_handoff',
                    reason='service_window_expired',
                    risk_level='medium',
                )

    # Rule 4: bot turns >= max_bot_turns.
    bot_turn_count = int(conversation.get('bot_turn_count') or 0)
    if bot_turn_count >= max_bot_turns:
        return PolicyResult(
            action='require_handoff',
            reason=f'max_bot_turns_exceeded:{bot_turn_count}/{max_bot_turns}',
            risk_level='medium',
        )

    # Rule 5: consecutive no-context responses.
    consecutive_no_context = int(conversation.get('consecutive_no_context') or 0)
    if consecutive_no_context >= consecutive_no_context_limit:
        return PolicyResult(
            action='require_handoff',
            reason=f'consecutive_no_context:{consecutive_no_context}/{consecutive_no_context_limit}',
            risk_level='medium',
        )

    return PolicyResult(
        action='continue_bot',
        reason='all_policies_passed',
        risk_level='low',
    )


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def _to_positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
