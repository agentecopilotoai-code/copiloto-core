"""Static analysis and unit tests for the WhatsApp RAG inbound orchestrator (TASK-0021)."""
from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source

ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
# ── Static source checks ──────────────────────────────────────────────────────

def test_orchestrator_is_called_from_webhook_after_inbound_message_is_saved():
    source = routes_aggregated_source()

    assert 'from app.services.rag_orchestrator import orchestrate_inbound_message' in source
    assert 'await orchestrate_inbound_message(' in source
    # Called only when inbound_message was actually inserted
    assert 'if inbound_message:' in source


def test_webhook_channel_query_fetches_account_mode():
    source = routes_aggregated_source()

    assert 'select id, tenant_id, app_secret_ref, account_mode' in source


def test_orchestrator_skips_non_text_and_empty_messages():
    source = ORCHESTRATOR.read_text()

    # Interactive replies (button_reply/list_reply) are treated as text after
    # the webhook fills body_text with the interactive title; everything else
    # is skipped as non_text_message.
    assert "message_type'] not in ('text', 'interactive')" in source
    assert "'non_text_message'" in source


def test_orchestrator_skips_human_active_conversations():
    source = ORCHESTRATOR.read_text()

    assert "conversation['status'] == 'human_active'" in source
    assert "'human_active'" in source


def test_orchestrator_skips_suppressed_and_revoked_contacts():
    """TASK-0062: the legacy inline opt-in skip was replaced by
    ``enforce_inbound_consent`` which returns ``contact_opt_in_revoked`` /
    ``contact_opt_in_suppressed`` for revoked/suppressed contacts."""
    source = ORCHESTRATOR.read_text()
    consent_source = (Path(__file__).parent.parent / 'app' / 'services' / 'consent.py').read_text()

    # Orchestrator delegates the gate.
    assert 'enforce_inbound_consent' in source
    # The consent service is the one checking revoked / suppressed status.
    assert "opt_in in ('revoked', 'suppressed')" in consent_source


def test_orchestrator_reads_escalation_policy_from_tenant_settings():
    source = ORCHESTRATOR.read_text()

    assert 'escalation_policy' in source
    assert 'tenant_settings' in source
    assert '_parse_escalation_policy' in source
    # max_bot_turns is no longer a separate column — value lives inside escalation_policy.triggers.after_bot_turns.
    assert 'ts.max_bot_turns' not in source


def test_orchestrator_checks_keyword_triggers_from_policy_engine():
    source = ORCHESTRATOR.read_text()
    policy_source = (Path(__file__).parent.parent / 'app' / 'services' / 'policy_engine.py').read_text()

    # Keyword escalation handled exclusively by policy engine reading triggers.keywords.
    assert 'evaluate_policy' in source
    assert "triggers.get('keywords')" in policy_source
    # No keyword-trigger helper or hardcoded defaults in the orchestrator.
    assert '_keyword_triggers' not in source
    assert '_DEFAULT_HUMAN_KEYWORDS' not in source


def test_orchestrator_enforces_after_bot_turns_limit():
    source = ORCHESTRATOR.read_text()
    policy_source = (Path(__file__).parent.parent / 'app' / 'services' / 'policy_engine.py').read_text()

    # Bot turn count is fetched in orchestrator and passed to evaluate_policy.
    assert 'bot_turn_count' in source
    assert "sender_actor_type='bot'" in source
    # Max turns enforcement now delegated to policy engine which reads triggers.after_bot_turns.
    assert 'max_bot_turns_exceeded' in policy_source
    assert "triggers.get('after_bot_turns')" in policy_source
    assert 'evaluate_policy' in source


def test_orchestrator_resets_bot_turn_count_after_release():
    """When a human takes over and releases the conversation back to the bot,
    the policy counters must restart from the most recent release timestamp —
    otherwise every new message after a release would re-trigger handoff."""
    source = ORCHESTRATOR.read_text()

    assert 'last_release_at' in source
    assert "from app.handoffs" in source
    assert "status='resolved'" in source
    assert "max(updated_at)" in source
    # Both the count and the consecutive-no-context query honour the window.
    assert source.count('$2::timestamptz is null or created_at > $2') >= 2


def test_orchestrator_deduplicates_by_idempotency_key():
    source = ORCHESTRATOR.read_text()

    assert "f'bot_reply:{inbound_message" in source
    assert "'already_processed'" in source
    assert 'on conflict (tenant_id, idempotency_key) do nothing' in source


def test_orchestrator_queries_active_knowledge_chunks_for_tenant():
    source = ORCHESTRATOR.read_text()

    assert 'from app.knowledge_chunks kc' in source
    assert "kd.status='active'" in source
    assert 'rank_chunks' in source
    assert 'build_grounded_answer' in source


def test_orchestrator_creates_outbound_bot_message_and_enqueues_domain_event():
    source = ORCHESTRATOR.read_text()

    assert "direction, sender_actor_type" in source
    assert "'outbound', 'bot'" in source
    assert "status, payload" in source
    assert "'message.queued'" in source
    assert "insert into app.domain_events" in source
    assert 'aggregate_type' in source


def test_orchestrator_includes_rag_trace_in_outbound_message_payload():
    source = ORCHESTRATOR.read_text()

    assert "'rag_decision'" in source
    assert "'top_score'" in source
    assert "'top_document'" in source
    assert "'chunks_used'" in source
    assert "'inbound_message_id'" in source
    assert 'retrieval_match_to_dict' in source


def test_orchestrator_audits_bot_reply_and_handoff_decisions():
    source = ORCHESTRATOR.read_text()

    assert 'from app.services.audit import audit' in source
    assert "'bot.replied'" in source
    assert "'bot.handoff'" in source
    assert "actor_type='bot'" in source
    assert "actor_id='rag_orchestrator'" in source


def test_orchestrator_creates_handoff_record_when_context_is_insufficient():
    source = ORCHESTRATOR.read_text()

    assert 'insert into app.handoffs' in source
    assert "'knowledge_context_insufficient'" in source
    assert 'handoff_required=true' in source
    assert "status='waiting_agent'" in source


def test_orchestrator_sends_handoff_message_if_policy_defines_one():
    source = ORCHESTRATOR.read_text()

    assert "handoff_message" in source
    assert "f'handoff_msg:{inbound_message" in source
    assert 'handoff_message_sent' in source


def test_orchestrator_does_not_create_duplicate_handoff_if_one_is_already_open():
    source = ORCHESTRATOR.read_text()

    assert "status='open'" in source
    assert 'existing_handoff' in source
    assert 'handoff_id = existing_handoff' in source


def test_orchestrator_errors_are_caught_and_logged_without_failing_the_webhook():
    source = routes_aggregated_source()

    assert 'log.exception(' in source
    assert "'rag_orchestrator.error'" in source


# ── Unit tests for pure helper functions ─────────────────────────────────────

def test_parse_escalation_policy_handles_string_json():
    import json
    from app.services.rag_orchestrator import _parse_escalation_policy

    raw = json.dumps({'enabled': True, 'queue': 'support'})
    result = _parse_escalation_policy(raw)

    assert result['enabled'] is True
    assert result['queue'] == 'support'


def test_parse_escalation_policy_handles_invalid_string():
    from app.services.rag_orchestrator import _parse_escalation_policy

    assert _parse_escalation_policy('not-json') == {}
    assert _parse_escalation_policy(None) == {}
    assert _parse_escalation_policy([]) == {}


def test_trigger_keywords_trigger_handoff_via_policy_engine():
    from app.services.policy_engine import evaluate_policy

    settings = {
        'escalation_policy': {
            'triggers': {'keywords': ['humano', 'asesor', 'agente', 'reclamo'], 'after_bot_turns': 99},
        },
    }
    conv = {'bot_turn_count': 0, 'consecutive_no_context': 0, 'service_window_expires_at': None}

    for kw in ['humano', 'asesor', 'agente', 'reclamo']:
        result = evaluate_policy(settings, conv, f'quiero un {kw}', 'faq')
        assert result.action == 'require_handoff', f'keyword {kw!r} debería disparar handoff'


def test_no_trigger_keywords_continues_bot():
    from app.services.policy_engine import evaluate_policy

    settings = {
        'escalation_policy': {
            'triggers': {'keywords': ['demanda'], 'after_bot_turns': 99},
        },
    }
    conv = {'bot_turn_count': 0, 'consecutive_no_context': 0, 'service_window_expires_at': None}

    result = evaluate_policy(settings, conv, 'tengo una pregunta sobre precios', 'faq')
    assert result.action == 'continue_bot'


def test_policy_engine_ignores_unknown_top_level_fields():
    """Engine reads only triggers.keywords — unknown top-level fields are noise."""
    from app.services.policy_engine import evaluate_policy

    settings = {
        'escalation_policy': {
            'unrelated_keywords': ['demanda'],  # arbitrary unknown field
            'triggers': {'keywords': [], 'after_bot_turns': 99},
            'enforce_service_window': False,
        },
    }
    conv = {'bot_turn_count': 0, 'consecutive_no_context': 0, 'service_window_expires_at': None}
    result = evaluate_policy(settings, conv, 'voy a poner una demanda', 'faq')
    assert result.action == 'continue_bot'


def test_rag_retrieval_answers_manicure_price_from_indexed_csv_chunk():
    """Simulates the main acceptance criterion: manicure price query answered from knowledge."""
    from app.services.rag_retrieval import rank_chunks, build_grounded_answer
    from uuid import uuid4

    document_id = uuid4()
    chunks = [
        {
            'id': uuid4(),
            'document_id': document_id,
            'document_title': 'Precios Servicios Salón',
            'source_uri': 'uploads/precios.csv',
            'source_type': 'upload',
            'document_type': 'reference',
            'visibility': 'tenant',
            'chunk_index': 0,
            'section_path': 'Servicios y Precios',
            'chunk_text': 'Manicure clásica: $25.000. Manicure semipermanente: $45.000. Pedicure: $30.000.',
            'token_count': 20,
            'metadata': {},
        }
    ]

    matches = rank_chunks('¿Qué precio tiene una manicure?', chunks)
    decision = build_grounded_answer('¿Qué precio tiene una manicure?', matches)

    assert decision['sufficient_context'] is True
    assert decision['status'] == 'answered'
    assert decision['answer'] is not None
    assert 'Manicure' in decision['answer']
    assert '_source_document' in decision
    assert decision['handoff']['required'] is False


def test_rag_retrieval_escalates_when_question_has_no_evidence():
    """Question outside knowledge base triggers handoff decision."""
    from app.services.rag_retrieval import rank_chunks, build_grounded_answer
    from uuid import uuid4

    chunks = [
        {
            'id': uuid4(),
            'document_id': uuid4(),
            'document_title': 'Horarios',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'reference',
            'visibility': 'tenant',
            'chunk_index': 0,
            'section_path': None,
            'chunk_text': 'Atendemos de lunes a viernes de 9am a 6pm.',
            'token_count': 12,
            'metadata': {},
        }
    ]

    matches = rank_chunks('¿Tienen servicio de spa para perros?', chunks)
    decision = build_grounded_answer('¿Tienen servicio de spa para perros?', matches)

    assert decision['sufficient_context'] is False
    assert decision['status'] == 'escalate_to_human'
    assert decision['handoff']['required'] is True
    assert decision['answer'] is None


def test_rag_retrieval_duplicate_question_returns_same_decision():
    """Same question twice produces the same decision (deterministic ranking)."""
    from app.services.rag_retrieval import rank_chunks, build_grounded_answer
    from uuid import uuid4

    document_id = uuid4()
    chunks = [
        {
            'id': uuid4(),
            'document_id': document_id,
            'document_title': 'Precios',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'reference',
            'visibility': 'tenant',
            'chunk_index': 0,
            'section_path': 'Manicure',
            'chunk_text': 'Manicure básica cuesta $20.000.',
            'token_count': 10,
            'metadata': {},
        }
    ]

    question = '¿Cuánto cuesta la manicure?'
    decision_1 = build_grounded_answer(question, rank_chunks(question, chunks))
    decision_2 = build_grounded_answer(question, rank_chunks(question, chunks))

    assert decision_1['sufficient_context'] == decision_2['sufficient_context']
    assert decision_1['status'] == decision_2['status']
    assert decision_1['answer'] == decision_2['answer']
