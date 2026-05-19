"""Platform filter regex patterns extracted from app/api/v1/routes.py."""
from __future__ import annotations

import re


# `authenticate_request` + `require_platform_owner` + `require_mfa_for_privileged`
# dependencies already enforce that ONLY a platform_owner with verified MFA can
# read across tenants — never relaxed at the handler level.
_FLEET_LIST_STATUS_PATTERN = re.compile(r'^(trial|active|suspended|churned)$')

# `app.support_mode` — operator_alerts has RLS and a nullable `tenant_id` for
# system-level alerts; the schema comment notes that surfacing NULL-tenant rows
# under `app.support_mode()` is the expected operator path (TASK-0064).
_INCIDENT_STATUS_PATTERN = re.compile(r'^(pending|sent|failed)$')
_INCIDENT_KIND_PATTERN = re.compile(
    r'^(negative_feedback|complaint|backup_failure|outbound_dlq_threshold)$'
)

# Why the tenant-wide export is NOT enough: a Ley 1581 / GDPR access request
# requires the data of the ONE complainant. Sending the full dump exposes
# every OTHER contact's PII and creates a worse violation than the one the
# claimant was reporting. The runbook now points here.
_CONTACT_EXPORT_ALLOWED_KINDS = ('consent_ledger', 'messages', 'appointments', 'subscriptions')
