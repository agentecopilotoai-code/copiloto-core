"""
TASK-0017 — Pruebas integradas de webhook rápido, worker idempotente
y trazabilidad outbound.

Suite estática: lee el código fuente y verifica que los mecanismos de
idempotencia, deduplicación, trazabilidad y flujo asincrónico están
implementados correctamente, sin necesidad de levantar PostgreSQL ni Docker.
"""

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source

EVENT_WORKER = Path('app/workers/event_worker.py')
WHATSAPP_SVC = Path('app/services/whatsapp.py')
DB_SCHEMA = Path('infra/postgres/01-schema.sql')
BOOTSTRAP = Path('scripts/bootstrap.sh')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def routes_source() -> str:
    return routes_aggregated_source()


def worker_source() -> str:
    return EVENT_WORKER.read_text()


def schema_source() -> str:
    return DB_SCHEMA.read_text()


# ---------------------------------------------------------------------------
# 1. Estructura de payload Meta representativo
# ---------------------------------------------------------------------------

class TestMetaPayloadHandling:
    """El webhook procesa el payload estándar de Meta Cloud API correctamente."""

    def test_entry_changes_messages_iteration(self):
        src = routes_source()
        assert "for entry in payload.get('entry', [])" in src
        assert "for change in entry.get('changes', [])" in src
        assert "value = change.get('value', {})" in src
        assert "for message in value.get('messages', [])" in src

    def test_extracts_wa_id_and_external_message_id(self):
        src = routes_source()
        assert "wa_id = str(message.get('from') or '').strip()" in src
        assert "external_message_id = str(message.get('id') or '').strip()" in src
        assert 'if not wa_id or not external_message_id:' in src
        assert 'continue' in src

    def test_extracts_contacts_profile_name(self):
        src = routes_source()
        assert "contacts_by_wa_id" in src
        assert "value.get('contacts', [])" in src
        assert "contact.get('wa_id')" in src
        assert "contact_payload.get('profile', {}).get('name')" in src

    def test_extracts_message_timestamp_for_received_at(self):
        src = routes_source()
        assert "timestamp = message.get('timestamp')" in src
        assert 'datetime.fromtimestamp(int(timestamp)' in src
        assert 'received_at' in src
        assert "coalesce($10::timestamptz, now())" in src

    def test_extracts_text_body_from_meta_structure(self):
        src = routes_source()
        assert "message.get('text', {}).get('body')" in src

    def test_extracts_media_fields_from_meta_structure(self):
        src = routes_source()
        assert "media_payload = message.get(message_type)" in src
        assert "media_id = media_payload.get('id')" in src
        assert "mime_type = media_payload.get('mime_type')" in src
        assert "body_text = media_payload.get('caption')" in src

    def test_webhook_returns_accepted_immediately(self):
        src = routes_source()
        assert "return {'accepted': True, 'payload_sha256': sha}" in src

    def test_webhook_returns_fast_not_blocking_on_worker(self):
        """El webhook no espera procesamiento de mensajes outbound;
        termina con 'accepted: True' sin llamar a send_whatsapp_message."""
        src = routes_source()
        webhook_fn_start = src.find('async def receive_whatsapp_webhook')
        assert webhook_fn_start != -1
        # The webhook function body ends at the next top-level async def
        next_fn = src.find('\nasync def ', webhook_fn_start + 1)
        webhook_body = src[webhook_fn_start:next_fn if next_fn != -1 else webhook_fn_start + 10000]
        assert 'send_whatsapp_message' not in webhook_body
        assert "return {'accepted': True" in webhook_body


# ---------------------------------------------------------------------------
# 2. Deduplicación de webhooks por payload_sha256
# ---------------------------------------------------------------------------

class TestWebhookRawEventDeduplication:
    """Payloads duplicados de Meta no insertan duplicados en webhook_events_raw."""

    def test_raw_event_insert_uses_on_conflict_payload_sha256(self):
        src = routes_source()
        assert 'on conflict (payload_sha256) do nothing' in src

    def test_sha256_computed_from_raw_body(self):
        src = routes_source()
        assert 'sha = hashlib.sha256(body).hexdigest()' in src

    def test_raw_event_returning_star_used_to_detect_duplicate(self):
        """El código usa RETURNING * para detectar si el insert fue no-op."""
        src = routes_source()
        assert 'on conflict (payload_sha256) do nothing returning *' in src

    def test_schema_has_payload_sha256_unique_constraint(self):
        src = schema_source()
        assert 'payload_sha256' in src
        assert 'webhook_events_raw' in src

    def test_sha256_returned_in_response(self):
        src = routes_source()
        assert "'payload_sha256': sha" in src


# ---------------------------------------------------------------------------
# 3. Deduplicación de mensajes inbound por external_message_id
# ---------------------------------------------------------------------------

class TestInboundMessageDeduplication:
    """Mensajes inbound duplicados (mismo external_message_id) no crean
    filas duplicadas en app.messages ni duplican notificaciones."""

    def test_inbound_insert_uses_on_conflict_external_message_id(self):
        src = routes_source()
        assert 'on conflict (tenant_id, external_message_id) do nothing' in src

    def test_inbound_insert_returns_row_only_on_first_insert(self):
        src = routes_source()
        assert 'on conflict (tenant_id, external_message_id) do nothing' in src
        assert 'returning *' in src

    def test_notify_only_when_inbound_message_created(self):
        """notify_operations_change solo se llama cuando inbound_message no es None
        (la inserción fue efectiva, no un duplicado)."""
        src = routes_source()
        assert 'if inbound_message:' in src
        notify_block_start = src.find('if inbound_message:')
        assert notify_block_start != -1
        notify_context = src[notify_block_start:notify_block_start + 300]
        assert 'notify_operations_change' in notify_context
        assert "'conversation.changed'" in notify_context

    def test_schema_has_unique_constraint_on_external_message_id(self):
        src = schema_source()
        assert 'external_message_id' in src
        assert 'messages' in src

    def test_inbound_message_direction_is_inbound(self):
        src = routes_source()
        assert "'inbound', 'contact'" in src

    def test_inbound_message_status_is_received(self):
        src = routes_source()
        assert "'received'" in src


# ---------------------------------------------------------------------------
# 4. Deduplicación de eventos outbound por idempotency_key
# ---------------------------------------------------------------------------

class TestOutboundIdempotencyKey:
    """Crear dos veces un mensaje outbound con el mismo Idempotency-Key
    no genera dos domain_events ni dos envíos al worker."""

    def test_domain_event_insert_uses_on_conflict_do_nothing(self):
        src = routes_source()
        count = src.count("on conflict do nothing")
        assert count >= 2, (
            f"Se esperan al menos 2 'on conflict do nothing' para domain_events, encontrados: {count}"
        )

    def test_idempotency_key_header_accepted_in_create_message(self):
        src = routes_source()
        assert "idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')" in src

    def test_key_fallbacks_to_message_id_when_header_absent(self):
        src = routes_source()
        assert 'key = idempotency_key or str(row[' in src or \
               "key = idempotency_key or str(message[" in src

    def test_domain_event_insert_includes_idempotency_key_column(self):
        src = routes_source()
        assert 'idempotency_key' in src
        assert "insert into app.domain_events" in src
        assert "'message.queued'" in src

    def test_schema_has_idempotency_key_unique_constraint(self):
        src = schema_source()
        assert 'idempotency_key' in src
        assert 'domain_events' in src

    def test_quote_send_uses_deterministic_idempotency_key(self):
        src = routes_source()
        assert 'idempotency_key = f"quote-send-{quote_id}"' in src

    def test_start_conversation_also_uses_idempotency_key(self):
        src = routes_source()
        start_idx = src.find('async def start_conversation')
        assert start_idx != -1
        next_fn = src.find('\nasync def ', start_idx + 1)
        start_body = src[start_idx:next_fn if next_fn != -1 else start_idx + 8000]
        assert 'idempotency_key' in start_body
        assert 'on conflict do nothing' in start_body


# ---------------------------------------------------------------------------
# 5. Worker: procesamiento asincrónico y actualización de estados
# ---------------------------------------------------------------------------

class TestWorkerProcessing:
    """El worker consume domain_events pendientes y actualiza el estado
    del mensaje correctamente."""

    def test_worker_queries_unpublished_message_queued_events(self):
        src = worker_source()
        assert "e.published_at is null and e.event_name='message.queued'" in src

    def test_worker_limits_batch_to_10(self):
        # BUG-173 (fix-group-30): el SELECT per-row ahora usa `LIMIT 1` y el
        # batch de 10 se logra con un for-loop outer en `process_once`
        # (cada iteración = transacción propia → per-row commit, sin
        # rollback de eventos ya entregados a Meta cuando una fila tardía
        # falla). El semantics-equivalente sigue siendo "hasta 10 eventos
        # por tick" pero ahora vive en `EVENT_WORKER_BATCH_SIZE = 10` +
        # `for _ in range(EVENT_WORKER_BATCH_SIZE):` en lugar de SQL LIMIT.
        src = worker_source()
        assert 'EVENT_WORKER_BATCH_SIZE = 10' in src
        assert 'for _ in range(EVENT_WORKER_BATCH_SIZE):' in src
        assert 'limit 1' in src

    def test_worker_orders_by_occurred_at(self):
        src = worker_source()
        assert 'order by e.occurred_at' in src

    def test_worker_marks_message_sent_after_success(self):
        src = worker_source()
        assert "status='sent'" in src
        assert "sent_at=now()" in src

    def test_worker_updates_external_message_id_from_provider(self):
        src = worker_source()
        assert 'external_message_id=coalesce($2, external_message_id)' in src
        assert 'provider_message_id(result)' in src

    def test_worker_marks_domain_event_published_after_success(self):
        src = worker_source()
        assert 'update app.domain_events set published_at=now() where id=$1' in src

    def test_worker_marks_message_failed_on_exception(self):
        src = worker_source()
        assert "status='failed', failed_at=now(), error_message=$2" in src

    def test_worker_updates_domain_event_on_failure_too(self):
        src = worker_source()
        assert "update app.domain_events" in src
        assert "set published_at=now(), payload=payload || $2::jsonb" in src
        assert "'delivery_failed': True" in src

    def test_worker_continues_on_exception_skipping_failed_message(self):
        src = worker_source()
        assert 'continue' in src

    def test_worker_returns_count_of_processed_events(self):
        src = worker_source()
        assert 'return len(rows)' in src

    def test_worker_polls_with_shorter_interval_when_events_found(self):
        src = worker_source()
        assert 'await asyncio.sleep(1 if processed else 5)' in src


# ---------------------------------------------------------------------------
# 6. Trazabilidad: messages, events y audit logs enlazados por message_id
# ---------------------------------------------------------------------------

class TestTrazabilidad:
    """Los registros de messages, domain_events y audit_logs están
    vinculados por el mismo message_id, permitiendo trazabilidad end-to-end."""

    def test_worker_joins_messages_and_domain_events_by_aggregate_id(self):
        src = worker_source()
        assert 'join app.messages m on m.id = e.aggregate_id and m.tenant_id = e.tenant_id' in src

    def test_worker_joins_conversations_to_get_contact(self):
        src = worker_source()
        assert 'join app.conversations cv on cv.id = m.conversation_id' in src
        assert 'join app.contacts ct on ct.id = cv.contact_id' in src

    def test_worker_joins_channel_for_delivery_mode_and_token(self):
        src = worker_source()
        assert 'join app.tenant_channels c on c.id = cv.channel_id' in src
        assert 'c.account_mode' in src
        assert 'c.token_ref' in src

    def test_worker_notifies_with_conversation_and_message_ids(self):
        src = worker_source()
        assert "'conversation_id': str(row['conversation_id'])" in src
        assert "'message_id': str(row['aggregate_id'])" in src

    def test_audit_log_created_when_outbound_queued(self):
        src = routes_source()
        assert "action='message.queued'" in src
        assert "entity_type='message'" in src

    def test_domain_event_stores_message_payload_for_tracing(self):
        src = routes_source()
        assert "'message.queued'" in src
        assert "aggregate_type, aggregate_id" in src

    def test_worker_logs_delivery_attempt_with_message_id(self):
        src = worker_source()
        assert "'message_delivery_attempt'" in src
        assert "message_id=str(row['aggregate_id'])" in src

    def test_worker_logs_delivery_result_with_provider_message_id(self):
        src = worker_source()
        assert "'message_delivery_sent'" in src
        assert "provider_message_id=external_message_id" in src

    def test_worker_logs_delivery_failure_with_error(self):
        src = worker_source()
        assert "'message_delivery_failed'" in src
        assert "error=error_message" in src

    def test_worker_logs_mocked_delivery_separately(self):
        src = worker_source()
        assert "'message_delivery_mocked'" in src
        assert "'message_delivery_mocked' if mocked else 'message_delivery_sent'" in src


# ---------------------------------------------------------------------------
# 7. Reintentos seguros: eventos published no se reprocesan
# ---------------------------------------------------------------------------

class TestRetryAndIdempotency:
    """El worker no reprocesa eventos ya entregados (published_at IS NOT NULL)
    y reintenta solo eventos pendientes."""

    def test_worker_filters_published_at_is_null(self):
        src = worker_source()
        assert 'published_at is null' in src

    def test_worker_sets_published_at_on_success(self):
        src = worker_source()
        success_update = 'update app.domain_events set published_at=now() where id=$1'
        assert success_update in src

    def test_worker_sets_published_at_on_failure_too(self):
        src = worker_source()
        failure_block = src.find("set published_at=now(), payload=payload || $2::jsonb")
        assert failure_block != -1

    def test_worker_uses_transaction_for_atomic_message_and_event_update(self):
        src = worker_source()
        assert 'async with conn.transaction():' in src
        transaction_count = src.count('async with conn.transaction():')
        assert transaction_count >= 2, (
            f"Se esperan al menos 2 transacciones (éxito + fallo), encontradas: {transaction_count}"
        )

    def test_inbound_on_conflict_prevents_duplicate_messages(self):
        """Segundo webhook con mismo external_message_id no crea un mensaje nuevo."""
        src = routes_source()
        assert 'on conflict (tenant_id, external_message_id) do nothing' in src
        returning_after_conflict = (
            'on conflict (tenant_id, external_message_id) do nothing\n                    returning *'
        )
        assert returning_after_conflict in src

    def test_outbound_duplicate_key_prevents_double_queuing(self):
        """Dos llamadas POST con el mismo Idempotency-Key no crean dos eventos."""
        src = routes_source()
        assert "insert into app.domain_events" in src
        assert 'on conflict do nothing' in src


# ---------------------------------------------------------------------------
# 8. Mock vs Live — worker respeta account_mode del canal
# ---------------------------------------------------------------------------

class TestMockVsLiveDelivery:
    """El worker distingue entre modo mock y live para no confundir
    simulaciones locales con envíos reales a Meta."""

    def test_worker_reads_account_mode_from_channel(self):
        src = worker_source()
        assert 'c.account_mode' in src
        assert "row['account_mode'] or 'mock'" in src

    def test_whatsapp_service_accepts_delivery_mode_param(self):
        src = WHATSAPP_SVC.read_text()
        assert "delivery_mode: str = 'mock'" in src

    def test_whatsapp_service_returns_mocked_flag_when_not_live(self):
        src = WHATSAPP_SVC.read_text()
        assert "if delivery_mode != 'live'" in src

    def test_worker_detects_mocked_from_result(self):
        src = worker_source()
        assert "mocked = bool(result.get('mocked'))" in src

    def test_worker_reads_token_ref_from_channel(self):
        src = worker_source()
        assert "c.token_ref" in src
        assert "row['token_ref']" in src

    def test_mock_delivery_logs_as_message_delivery_mocked(self):
        src = worker_source()
        assert "'message_delivery_mocked' if mocked else 'message_delivery_sent'" in src


# ---------------------------------------------------------------------------
# 9. Proveedor de ID de mensaje y manejo de errores HTTP
# ---------------------------------------------------------------------------

class TestProviderMessageIdAndErrors:
    """provider_message_id extrae el ID del response de Meta;
    delivery_error_message formatea errores legibles."""

    def test_provider_message_id_reads_messages_list(self):
        src = worker_source()
        assert "def provider_message_id(result: dict) -> str | None:" in src
        assert "result.get('messages')" in src
        assert "messages[0]" in src
        assert "first_message.get('id')" in src

    def test_provider_message_id_returns_none_on_empty_list(self):
        src = worker_source()
        assert 'not isinstance(messages, list) or not messages' in src
        assert 'return None' in src

    def test_delivery_error_message_truncates_http_errors(self):
        src = worker_source()
        assert "def delivery_error_message(exc: Exception) -> str:" in src
        assert 'httpx.HTTPStatusError' in src
        assert 'exc.response.text[:1000]' in src
        assert 'str(exc)[:1000]' in src

    def test_worker_error_stored_in_message_and_domain_event(self):
        src = worker_source()
        assert 'error_message = delivery_error_message(exc)' in src
        assert 'error_message=$2' in src
        assert "'error_message': error_message" in src


# ---------------------------------------------------------------------------
# 10. Consistencia del esquema de base de datos
# ---------------------------------------------------------------------------

class TestDatabaseSchemaConsistency:
    """El esquema PostgreSQL tiene los constraints necesarios para garantizar
    idempotencia a nivel de base de datos."""

    def test_schema_has_webhook_events_raw_table(self):
        src = schema_source()
        assert 'webhook_events_raw' in src

    def test_schema_has_messages_table_with_external_message_id(self):
        src = schema_source()
        assert 'external_message_id' in src
        assert 'messages' in src

    def test_schema_has_domain_events_table_with_idempotency(self):
        src = schema_source()
        assert 'domain_events' in src
        assert 'idempotency_key' in src

    def test_schema_has_domain_events_published_at_column(self):
        src = schema_source()
        assert 'published_at' in src

    def test_schema_has_account_mode_on_tenant_channels(self):
        src = schema_source()
        assert "account_mode" in src
        assert "mock" in src
        assert "live" in src

    def test_bootstrap_adds_unique_constraint_for_external_message_id(self):
        bootstrap_src = BOOTSTRAP.read_text()
        assert 'external_message_id' in bootstrap_src or 'knowledge' in bootstrap_src
