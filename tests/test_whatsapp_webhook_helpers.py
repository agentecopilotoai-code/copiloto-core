from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
WHATSAPP = Path('app/services/whatsapp.py')


def test_whatsapp_phone_number_id_extractor_uses_meta_metadata_path():
    source = API_ROUTES.read_text()

    assert 'def whatsapp_phone_number_id_from_payload' in source
    assert "payload.get('entry', [])" in source
    assert "entry.get('changes', [])" in source
    assert "value.get('metadata', {})" in source
    assert "metadata.get('phone_number_id')" in source
    assert 'return str(phone_number_id)' in source


def test_webhook_signature_normalizes_app_id_secret_pairs():
    source = WHATSAPP.read_text()
    routes_source = API_ROUTES.read_text()

    assert 'def normalize_meta_app_secret' in source
    assert "cleaned.split('|', 1)" in source
    assert 'normalized_secret = normalize_meta_app_secret(app_secret)' in source
    assert "hmac.new(\n        normalized_secret.encode(), body, hashlib.sha256\n    ).hexdigest()" in source
    assert 'normalize_meta_app_secret(payload.app_secret)' in routes_source
    assert "WHATSAPP_APP_SECRET" not in source


def test_verify_webhook_reads_verify_token_from_tenant_secret_only():
    source = API_ROUTES.read_text()

    assert "tenant_secret_ref(row['tenant_id'], 'whatsapp_verify_token')" in source
    assert 'hmac.compare_digest(verify_token, hub_verify_token)' in source
    assert 'verify_token_hash(hub_verify_token)' not in source
    assert 'WHATSAPP_VERIFY_TOKEN' not in source


def test_webhook_raw_event_insert_is_tenant_scoped_for_rls():
    source = API_ROUTES.read_text()

    assert "select set_config('app.support_mode', 'true', true)" in source
    assert "select set_config('app.tenant_id', $1, true)" in source
    assert 'insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)' in source
    assert "channel['tenant_id']" in source


def test_whatsapp_webhook_persists_inbound_messages_for_live_inbox():
    source = API_ROUTES.read_text()

    assert "for message in value.get('messages', [])" in source
    assert 'upsert_whatsapp_contact' in source
    assert 'where tenant_id=$1 and (wa_id=$2 or phone_e164=$3)' in source
    assert 'insert into app.conversations' in source
    assert 'insert into app.messages (' in source
    assert "status='human_active'" in source
    assert "'waiting_agent'" in source
    assert "pg_notify('tenant_operations_events'" in source
    assert "'conversation.changed'" in source
