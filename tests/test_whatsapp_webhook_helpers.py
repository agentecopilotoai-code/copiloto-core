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


def test_webhook_signature_uses_supplied_app_secret_without_splitting_pairs():
    source = WHATSAPP.read_text()

    assert 'def verify_signature_with_secret' in source
    assert "hmac.new(\n        app_secret.encode(), body, hashlib.sha256\n    ).hexdigest()" in source
    assert "app_secret.split('|')" not in source
    assert "WHATSAPP_APP_SECRET" not in source


def test_verify_webhook_reads_verify_token_from_tenant_secret_only():
    source = API_ROUTES.read_text()

    assert "tenant_secret_ref(row['tenant_id'], 'whatsapp_verify_token')" in source
    assert 'hmac.compare_digest(verify_token, hub_verify_token)' in source
    assert 'verify_token_hash(hub_verify_token)' not in source
    assert 'WHATSAPP_VERIFY_TOKEN' not in source
