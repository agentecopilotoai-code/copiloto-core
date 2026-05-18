"""HMAC signatures for data-export bundles (audit-trail integrity).

Used by SEC-010-EXPORT-FU (contact-scoped consent ledger export) and any
future export endpoint that needs to prove integrity of a JSON file shared
with an external party (claimant, court, regulator).

Wire format is RAW HEX-encoded HMAC-SHA256 — distinct from
`app/core/signed_cookies.py` which emits a self-contained `<payload>.<sig>`
format intended for HTTP cookies. Exports need the bare signature so
operators can paste it into reports / SIC filings / audit logs without
base64 padding ambiguity, and so verification via standard CLI tooling is
straightforward:

    jq -S -c '.data' archivo.json > canonical.json
    openssl dgst -sha256 -hmac "$JWT_SECRET" canonical.json
    # → SHA2-256(stdin)= <hex>
    # comparar contra metadata->>'signature' del audit_logs

The signature is keyed on `Settings.jwt_secret` (same key as the
session/auth subsystem). Rotation of that secret invalidates verification
of pre-rotation signatures — documented in `docs/runbooks/consent-violation-claim.md`.
This module is `routes.py`-importable but has NO HMAC inlined in routes
itself (defended by `tests/test_support_mode_toggle_static.py::test_no_inline_hmac_signing_outside_signed_cookies_module`).
"""
from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings


def sign_export_bundle(canonical_json: str) -> str:
    """HMAC-SHA256 of `canonical_json` under `Settings.jwt_secret`, hex-encoded.

    The caller is responsible for producing canonical JSON
    (`json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)`)
    so that two invocations on the same bundle produce the same signature.
    Without canonicalization, dict key order or whitespace drift between
    runs would break verification.
    """
    settings = get_settings()
    return hmac.new(
        settings.jwt_secret.encode('utf-8'),
        canonical_json.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
