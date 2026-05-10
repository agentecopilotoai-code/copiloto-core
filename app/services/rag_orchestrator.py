"""Orchestrates automatic bot replies and human handoffs for inbound WhatsApp messages."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from app.core.config import get_settings
from app.services.audit import audit
from app.services.conversation_flow import (
    STAGE_START,
    ConversationContext,
    format_history,
    get_context,
    has_booking_intent,
)
from app.services.llm_answer import build_conversational_llm_answer, build_llm_answer
from app.services.rag_retrieval import build_grounded_answer, rank_chunks, retrieval_match_to_dict

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()

_DEFAULT_HUMAN_KEYWORDS = {'humano', 'asesor', 'agente', 'reclamo', 'persona'}


def _parse_escalation_policy(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _keyword_triggers(policy: dict[str, Any]) -> set[str]:
    triggers = policy.get('triggers') or {}
    if isinstance(triggers, str):
        try:
            triggers = json.loads(triggers)
        except (json.JSONDecodeError, TypeError):
            triggers = {}
    keywords = triggers.get('keywords') or []
    result = {kw.strip().lower() for kw in keywords if isinstance(kw, str) and kw.strip()}
    return result or _DEFAULT_HUMAN_KEYWORDS


async def orchestrate_inbound_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: asyncpg.Record,
    contact: asyncpg.Record,
    inbound_message: asyncpg.Record,
) -> dict[str, Any]:
    """Decide whether to reply automatically via RAG/LLM or escalate to a human agent."""

    body_text: str = inbound_message['body_text'] or ''
    conversation_id = str(conversation['id'])
    message_id = str(inbound_message['id'])

    log.info(
        'orchestrator.received',
        tenant_id=str(tenant_id),
        conversation_id=conversation_id,
        message_id=message_id,
        message_type=inbound_message['message_type'],
        body_preview=body_text[:80],
        conversation_status=conversation['status'],
    )

    if inbound_message['message_type'] != 'text' or not body_text.strip():
        log.info('orchestrator.skip', reason='non_text_message', message_id=message_id)
        return {'action': 'skipped', 'reason': 'non_text_message'}

    if conversation['status'] == 'human_active':
        log.info('orchestrator.skip', reason='human_active', conversation_id=conversation_id)
        return {'action': 'skipped', 'reason': 'human_active'}

    # Don't re-run the bot when the conversation is already queued for a human.
    # Exception: if the handoff has been open for longer than bot_reopen_after_hours
    # with no agent picking it up, automatically re-engage the bot so the client
    # isn't left waiting indefinitely. 0 = never re-engage.
    if conversation['status'] == 'waiting_agent' and conversation.get('handoff_required'):
        settings_early = get_settings()
        reopen_hours = settings_early.bot_reopen_after_hours
        should_skip = True
        handoff_age_hours = await conn.fetchval(
            """
            select extract(epoch from (now() - created_at)) / 3600.0
            from app.handoffs
            where tenant_id=$1 and conversation_id=$2 and status='open'
            order by created_at asc
            limit 1
            """,
            tenant_id,
            conversation['id'],
        )
        log.info(
            'orchestrator.waiting_agent_check',
            conversation_id=conversation_id,
            handoff_age_hours=round(float(handoff_age_hours), 3) if handoff_age_hours is not None else None,
            reopen_after_hours=reopen_hours,
            will_reopen=handoff_age_hours is not None and (reopen_hours > 0 and handoff_age_hours >= reopen_hours),
            no_open_handoff=handoff_age_hours is None,
        )

        if handoff_age_hours is None:
            # No open handoff row exists — the conversation got into waiting_agent
            # without a real pending handoff (inconsistent state). Reset and let
            # the bot process the message normally.
            log.warning(
                'orchestrator.no_real_handoff_reset',
                conversation_id=conversation_id,
                detail='waiting_agent+handoff_required=true but no open handoff row found; resetting to open',
            )
            await conn.execute(
                "update app.conversations set status='open', handoff_required=false, updated_at=now() where tenant_id=$1 and id=$2",
                tenant_id,
                conversation['id'],
            )
            should_skip = False
        elif reopen_hours > 0 and handoff_age_hours >= reopen_hours:
            log.warning(
                'orchestrator.handoff_timeout_reopen',
                conversation_id=str(conversation['id']),
                handoff_age_hours=round(float(handoff_age_hours), 2),
                reopen_after_hours=reopen_hours,
            )
            await conn.execute(
                """
                update app.conversations
                set status='waiting_user', handoff_required=false, updated_at=now()
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                conversation['id'],
            )
            await conn.execute(
                """
                update app.handoffs
                set status='resolved', updated_at=now()
                where tenant_id=$1 and conversation_id=$2 and status='open'
                """,
                tenant_id,
                conversation['id'],
            )
            should_skip = False

        if should_skip:
            log.info(
                'orchestrator.skip',
                reason='waiting_agent_handoff_pending',
                conversation_id=conversation_id,
                reopen_after_hours=reopen_hours,
                hint=(
                    'Para liberar manualmente: POST /v1/conversations/{id}/release con X-Service-Token. '
                    f'Re-engagement automático en {reopen_hours}h si reopen_hours>0.'
                ) if reopen_hours > 0 else 'BOT_REOPEN_AFTER_HOURS=0: re-engagement desactivado.',
            )
            return {'action': 'skipped', 'reason': 'waiting_agent_handoff_pending'}

    opt_in = contact.get('opt_in_status') or 'unknown'
    if opt_in in ('revoked', 'suppressed'):
        log.info('orchestrator.skip', reason=f'contact_opt_in_{opt_in}', conversation_id=conversation_id)
        return {'action': 'skipped', 'reason': f'contact_opt_in_{opt_in}'}

    # Load tenant settings and tenant display name
    settings_row = await conn.fetchrow(
        """
        select ts.escalation_policy, ts.max_bot_turns,
               t.display_name as business_name, t.vertical_code
        from app.tenant_settings ts
        join app.tenants t on t.id = ts.tenant_id
        where ts.tenant_id=$1
        """,
        tenant_id,
    )
    if settings_row is None:
        log.warning(
            'orchestrator.no_tenant_settings',
            tenant_id=str(tenant_id),
            detail='fila en tenant_settings no encontrada — usando defaults (max_bot_turns=10)',
        )

    raw_policy = (settings_row['escalation_policy'] if settings_row else None) or {}
    policy = _parse_escalation_policy(raw_policy)

    # escalation_policy.triggers.after_bot_turns takes precedence over the column
    # so that the UI and the orchestrator always agree on the limit.
    col_max_turns: int = (settings_row['max_bot_turns'] if settings_row else None) or 10
    policy_max_turns = (policy.get('triggers') or {}).get('after_bot_turns')
    max_bot_turns: int = int(policy_max_turns) if isinstance(policy_max_turns, (int, float)) and policy_max_turns > 0 else col_max_turns
    business_name: str = (settings_row['business_name'] if settings_row else None) or 'nuestro negocio'
    vertical_code: str = (settings_row['vertical_code'] if settings_row else None) or 'beauty'

    log.info(
        'orchestrator.settings_loaded',
        tenant_id=str(tenant_id),
        max_bot_turns=max_bot_turns,
        business_name=business_name,
        answer_engine=get_settings().answer_engine,
        escalation_triggers=sorted(_keyword_triggers(policy)),
        has_handoff_message=bool(policy.get('handoff_message')),
    )

    # Keyword trigger check
    body_lower = body_text.lower()
    triggered_keyword = next((kw for kw in _keyword_triggers(policy) if kw in body_lower), None)
    if triggered_keyword:
        log.info('orchestrator.keyword_trigger', keyword=triggered_keyword, conversation_id=conversation_id)
        return await _do_handoff(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            conversation=conversation,
            inbound_message=inbound_message,
            policy=policy,
            reason='keyword_trigger',
            reason_detail=f'keyword={triggered_keyword}',
        )

    # Max bot turns check
    bot_turn_count: int = await conn.fetchval(
        """
        select count(*) from app.messages
        where conversation_id=$1
          and direction='outbound'
          and sender_actor_type='bot'
        """,
        conversation['id'],
    ) or 0

    log.info(
        'orchestrator.bot_turn_check',
        conversation_id=conversation_id,
        bot_turn_count=bot_turn_count,
        max_bot_turns=max_bot_turns,
        will_exceed=bot_turn_count >= max_bot_turns,
    )

    if bot_turn_count >= max_bot_turns:
        log.warning(
            'orchestrator.max_turns_exceeded',
            conversation_id=conversation_id,
            bot_turn_count=bot_turn_count,
            limit=max_bot_turns,
            tenant_id=str(tenant_id),
            hint='Aumenta max_bot_turns en tenant_settings o via PATCH /v1/tenants/{id}/settings',
        )
        return await _do_handoff(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            conversation=conversation,
            inbound_message=inbound_message,
            policy=policy,
            reason='max_bot_turns_exceeded',
            reason_detail=f'count={bot_turn_count},limit={max_bot_turns}',
        )

    # Idempotency check (deduplication)
    idempotency_key = f'bot_reply:{inbound_message["id"]}'
    if await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id, idempotency_key,
    ):
        log.info('orchestrator.skip', reason='already_processed', idempotency_key=idempotency_key)
        return {'action': 'skipped', 'reason': 'already_processed'}

    # Retrieve active knowledge chunks and run RAG ranking
    rows = await conn.fetch(
        """
        select kc.id, kc.document_id,
               kd.title as document_title, kd.source_uri, kd.source_type,
               kd.document_type, kd.visibility,
               kc.chunk_index, kc.section_path, kc.chunk_text, kc.token_count, kc.metadata
        from app.knowledge_chunks kc
        join app.knowledge_documents kd on kd.id = kc.document_id and kd.tenant_id = kc.tenant_id
        where kc.tenant_id=$1
          and kd.status='active'
        order by kd.updated_at desc, kc.chunk_index asc
        """,
        tenant_id,
    )
    chunks = [dict(row) for row in rows]
    matches = rank_chunks(body_text, chunks)

    settings = get_settings()
    engine = settings.answer_engine

    log.info(
        'orchestrator.rag_ranked',
        conversation_id=conversation_id,
        total_chunks=len(chunks),
        matches_above_llm_threshold=sum(1 for m in matches if m.score >= settings.cascade_llm_min_score),
        top_score=round(matches[0].score, 4) if matches else None,
        top_document=matches[0].document_title if matches else None,
        answer_engine=engine,
    )

    # ── Conversational booking flow ───────────────────────────────────────────
    ctx = get_context(conversation.get('metadata'))
    use_conversational = engine != 'template' and (
        ctx.stage == STAGE_START
        or ctx.is_conversational
        or has_booking_intent(body_text)
    )

    log.info(
        'orchestrator.routing',
        conversation_id=conversation_id,
        engine=engine,
        conv_stage=ctx.stage,
        is_conversational=ctx.is_conversational,
        has_booking_intent=has_booking_intent(body_text),
        use_conversational=use_conversational,
        collected_keys=list(ctx.collected.keys()),
    )

    if use_conversational:
        history_rows = await conn.fetch(
            """
            select direction, body_text from app.messages
            where conversation_id=$1
              and id != $2
              and body_text is not null
              and body_text != ''
            order by created_at asc
            limit 16
            """,
            conversation['id'],
            inbound_message['id'],
        )
        history = format_history([dict(r) for r in history_rows])

        log.info(
            'orchestrator.conversational_call',
            conversation_id=conversation_id,
            conv_stage=ctx.stage,
            history_turns=len(history_rows),
            llm_model=settings.local_llm_model,
            llm_url=settings.local_llm_base_url,
        )

        decision = await _resolve_conversational(
            body_text, matches, ctx, history, settings, business_name=business_name,
        )

        new_stage = decision.get('next_stage', ctx.stage)
        new_collected = decision.get('collected', ctx.collected)
        action = decision.get('action')

        log.info(
            'orchestrator.conversational_result',
            conversation_id=conversation_id,
            prev_stage=ctx.stage,
            next_stage=new_stage,
            action=action,
            sufficient_context=decision['sufficient_context'],
            answer_preview=(decision.get('answer') or '')[:120],
            collected_keys=list(new_collected.keys()),
        )

        await _update_conversation_metadata(
            conn, tenant_id, conversation, new_stage, new_collected,
        )

        if action == 'create_appointment':
            await _handle_appointment_created(
                conn,
                tenant_id=tenant_id,
                contact_id=contact['id'],
                conversation=conversation,
                inbound_message=inbound_message,
                collected=new_collected,
                vertical_code=vertical_code,
            )

        if action == 'request_human' or not decision['sufficient_context']:
            # When the LLM is down and the conversation hasn't started yet,
            # reply with a brief fallback greeting instead of immediately handing
            # off — the client shouldn't notice the backend is degraded on the
            # very first message.
            if ctx.stage == STAGE_START and action != 'request_human':
                fallback_greeting = (
                    f'¡Hola! 👋 Soy el asistente de {business_name}. '
                    'En este momento tengo dificultades técnicas para ayudarte completamente. '
                    '¿Podrías contarme en qué te puedo ayudar? Haré mi mejor esfuerzo 😊'
                )
                log.warning(
                    'orchestrator.start_stage_fallback_greeting',
                    conversation_id=conversation_id,
                    reason='llm_unavailable_at_start',
                )
                return await _send_bot_reply(
                    conn,
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    conversation=conversation,
                    inbound_message=inbound_message,
                    answer_text=fallback_greeting,
                    matches=matches,
                    idempotency_key=idempotency_key,
                    top_score=None,
                    top_document=None,
                    llm_used=False,
                    llm_model=None,
                    conv_stage=STAGE_START,
                )

            log.info(
                'orchestrator.conversational_handoff',
                conversation_id=conversation_id,
                trigger='request_human' if action == 'request_human' else 'insufficient_context',
                decision_reason=decision.get('reason'),
            )
            return await _do_handoff(
                conn,
                tenant_id=tenant_id,
                channel_id=channel_id,
                conversation=conversation,
                inbound_message=inbound_message,
                policy=policy,
                reason='user_requested_human' if action == 'request_human' else 'knowledge_context_insufficient',
                reason_detail=decision.get('reason', ''),
            )

        return await _send_bot_reply(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            conversation=conversation,
            inbound_message=inbound_message,
            answer_text=decision['answer'],
            matches=matches,
            idempotency_key=idempotency_key,
            top_score=matches[0].score if matches else None,
            top_document=matches[0].document_title if matches else None,
            llm_used=decision.get('llm_used', True),
            llm_model=decision.get('llm_model'),
            conv_stage=new_stage,
        )

    # ── Q&A cascade (template → LLM → handoff) ───────────────────────────────
    log.info('orchestrator.qa_cascade', conversation_id=conversation_id, engine=engine)
    decision = await _resolve_answer(body_text, matches, settings)

    top_score = matches[0].score if matches else None
    top_document = matches[0].document_title if matches else None

    log.info(
        'orchestrator.qa_result',
        conversation_id=conversation_id,
        sufficient_context=decision['sufficient_context'],
        status=decision.get('status'),
        reason=decision.get('reason'),
        llm_used=decision.get('llm_used', False),
    )

    if decision['sufficient_context']:
        return await _send_bot_reply(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            conversation=conversation,
            inbound_message=inbound_message,
            answer_text=decision['answer'],
            matches=matches,
            idempotency_key=idempotency_key,
            top_score=top_score,
            top_document=top_document,
            llm_used=decision.get('llm_used', False),
            llm_model=decision.get('llm_model'),
        )

    return await _do_handoff(
        conn,
        tenant_id=tenant_id,
        channel_id=channel_id,
        conversation=conversation,
        inbound_message=inbound_message,
        policy=policy,
        reason='knowledge_context_insufficient',
        reason_detail='no_active_evidence',
    )


async def _resolve_conversational(
    question: str,
    matches: list,
    ctx: ConversationContext,
    history: str,
    settings: Any,
    *,
    business_name: str,
) -> dict[str, Any]:
    """Call the conversational LLM with booking state; fall back to Q&A cascade on failure."""
    try:
        return await build_conversational_llm_answer(
            question,
            matches,
            ctx=ctx,
            history=history,
            base_url=settings.local_llm_base_url,
            model=settings.local_llm_model,
            timeout_seconds=settings.local_llm_timeout_seconds,
            min_score=settings.cascade_llm_min_score,
            business_name=business_name,
        )
    except Exception as exc:
        log.warning(
            'cascade.conversational_llm_unavailable',
            base_url=settings.local_llm_base_url,
            model=settings.local_llm_model,
            error=str(exc),
            hint=(
                'Verifica que Ollama esté corriendo en el HOST (no en Docker). '
                'En Linux usa LOCAL_LLM_BASE_URL=http://172.17.0.1:11434 '
                'En Mac/Windows usa http://host.docker.internal:11434'
            ),
        )
    # Ollama unavailable — fall through to Q&A cascade
    return await _resolve_answer(question, matches, settings)


async def _resolve_answer(
    question: str,
    matches: list,
    settings: Any,
) -> dict[str, Any]:
    """
    Cascade strategy:
      1. Template con umbral alto → respuesta gratis e instantánea.
      2. LLM local (Ollama) con umbral bajo → interpreta frases ambiguas.
      3. Si Ollama no está disponible → devuelve insufficient para que el
         caller haga handoff. Nunca lanza excepción.
    """
    engine = settings.answer_engine

    if engine == 'template':
        return build_grounded_answer(question, matches)

    if engine == 'local_llm':
        if not matches:
            return build_grounded_answer(question, matches)
        return await build_llm_answer(
            question, matches,
            base_url=settings.local_llm_base_url,
            model=settings.local_llm_model,
            timeout_seconds=settings.local_llm_timeout_seconds,
        )

    # cascade: template → llm → handoff
    template_decision = build_grounded_answer(
        question, matches, min_score=settings.cascade_template_min_score
    )
    top_score = matches[0].score if matches else None
    log.info(
        'cascade.template_attempt',
        top_score=round(top_score, 4) if top_score is not None else None,
        threshold=settings.cascade_template_min_score,
        answered=template_decision['sufficient_context'],
        total_chunks=len(matches),
    )
    if template_decision['sufficient_context']:
        log.info('cascade.template_answered', top_score=top_score)
        return template_decision

    llm_candidates = [m for m in matches if m.score >= settings.cascade_llm_min_score]
    log.info(
        'cascade.llm_attempt',
        llm_candidates=len(llm_candidates),
        llm_threshold=settings.cascade_llm_min_score,
        base_url=settings.local_llm_base_url,
        model=settings.local_llm_model,
    )
    if llm_candidates:
        try:
            llm_decision = await build_llm_answer(
                question, llm_candidates,
                base_url=settings.local_llm_base_url,
                model=settings.local_llm_model,
                timeout_seconds=settings.local_llm_timeout_seconds,
                min_score=settings.cascade_llm_min_score,
            )
            log.info(
                'cascade.llm_result',
                model=settings.local_llm_model,
                answered=llm_decision['sufficient_context'],
                status=llm_decision.get('status'),
            )
            if llm_decision['sufficient_context']:
                return llm_decision
        except Exception as exc:
            log.warning(
                'cascade.llm_unavailable',
                base_url=settings.local_llm_base_url,
                model=settings.local_llm_model,
                error=str(exc),
                hint=(
                    'Verifica que Ollama esté corriendo en el HOST. '
                    'Mac/Windows: http://host.docker.internal:11434 '
                    'Linux: http://172.17.0.1:11434'
                ),
            )
    else:
        log.info(
            'cascade.llm_skipped',
            reason='no_chunks_above_threshold',
            llm_threshold=settings.cascade_llm_min_score,
            total_chunks=len(matches),
            top_score=round(top_score, 4) if top_score is not None else None,
        )

    log.info('cascade.exhausted_to_handoff', question=question[:80], top_score=top_score)
    return {
        'status': 'escalate_to_human',
        'sufficient_context': False,
        'answer': None,
        'reason': 'Cascade agotado: template sin confianza suficiente y LLM no disponible o sin contexto.',
        'handoff': {'required': True, 'reason': 'cascade_exhausted'},
    }


async def _update_conversation_metadata(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    conversation: asyncpg.Record,
    new_stage: str,
    new_collected: dict[str, Any],
) -> None:
    """Merge conv_stage and collected into conversations.metadata jsonb."""
    raw_meta = conversation.get('metadata') or {}
    if isinstance(raw_meta, str):
        try:
            raw_meta = json.loads(raw_meta)
        except (json.JSONDecodeError, TypeError):
            raw_meta = {}
    meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
    meta['conv_stage'] = new_stage
    meta['collected'] = new_collected
    await conn.execute(
        """
        update app.conversations
        set metadata=$1::jsonb, updated_at=now()
        where tenant_id=$2 and id=$3
        """,
        json.dumps(meta),
        tenant_id,
        conversation['id'],
    )


async def _handle_appointment_created(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    conversation: asyncpg.Record,
    inbound_message: asyncpg.Record,
    collected: dict[str, Any],
    vertical_code: str,
) -> None:
    """Create a service_request from the bot-collected booking data.

    Full appointment scheduling (resource assignment, calendar blocking) requires
    human confirmation — the service_request lands in 'open' status for an agent
    to qualify and schedule via the admin panel.
    """
    idempotency_key = f'service_request:{inbound_message["id"]}'
    already_created = await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id, idempotency_key,
    )
    if already_created:
        return

    service_type = (
        collected.get('service_type')
        or collected.get('service_name')
        or 'consulta'
    )
    problem_summary = (
        collected.get('notes')
        or f"Solicitud de {collected.get('service_name', service_type)}"
    )

    sr = await conn.fetchrow(
        """
        insert into app.service_requests (
          tenant_id, contact_id, conversation_id,
          vertical_code, service_type, problem_summary,
          preferred_slot, status, intake
        )
        values ($1, $2, $3, $4, $5, $6, $7, 'open', $8::jsonb)
        returning id
        """,
        tenant_id,
        contact_id,
        conversation['id'],
        vertical_code,
        service_type,
        problem_summary,
        f"{collected.get('preferred_day', '')} {collected.get('preferred_time', '')}".strip() or None,
        json.dumps(collected),
    )

    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'service_request', $2, 'service_request.created', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        sr['id'],
        idempotency_key,
        json.dumps({'service_request_id': str(sr['id']), 'collected': collected}),
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='rag_orchestrator',
        action='bot.appointment_requested',
        entity_type='service_request',
        entity_id=str(sr['id']),
        metadata={
            'collected': collected,
            'inbound_message_id': str(inbound_message['id']),
        },
    )

    log.info(
        'rag_orchestrator.appointment_requested',
        tenant_id=str(tenant_id),
        service_request_id=str(sr['id']),
        service_type=service_type,
    )


async def _send_bot_reply(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: asyncpg.Record,
    inbound_message: asyncpg.Record,
    answer_text: str,
    matches: list,
    idempotency_key: str,
    top_score: float | None,
    top_document: str | None,
    llm_used: bool = False,
    llm_model: str | None = None,
    conv_stage: str | None = None,
) -> dict[str, Any]:
    trace_payload = {
        'rag_decision': 'answered',
        'answer_engine': 'local_llm' if llm_used else 'template',
        'llm_model': llm_model,
        'question': inbound_message['body_text'],
        'top_score': top_score,
        'top_document': top_document,
        'chunks_used': [retrieval_match_to_dict(m) for m in matches],
        'inbound_message_id': str(inbound_message['id']),
        'conv_stage': conv_stage,
    }
    outbound = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, 'text', 'queued', $4::jsonb)
        returning *
        """,
        tenant_id,
        conversation['id'],
        answer_text,
        json.dumps(trace_payload),
    )

    event_payload = {
        'message_id': str(outbound['id']),
        'conversation_id': str(conversation['id']),
        'body_text': answer_text,
        'channel_id': str(channel_id),
        'channel_account_mode': channel_account_mode,
    }
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        outbound['id'],
        idempotency_key,
        json.dumps(event_payload),
    )

    await conn.execute(
        """
        update app.conversations
        set status='waiting_user', handoff_required=false, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        conversation['id'],
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='rag_orchestrator',
        action='bot.replied',
        entity_type='message',
        entity_id=str(outbound['id']),
        metadata={
            'question': inbound_message['body_text'],
            'rag_decision': 'answered',
            'top_score': top_score,
            'top_document': top_document,
            'inbound_message_id': str(inbound_message['id']),
            'conv_stage': conv_stage,
        },
    )

    log.info(
        'rag_orchestrator.replied',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation['id']),
        top_score=top_score,
        conv_stage=conv_stage,
    )
    return {
        'action': 'bot_replied',
        'outbound_message_id': str(outbound['id']),
        'top_score': top_score,
        'top_document': top_document,
        'conv_stage': conv_stage,
    }


async def _do_handoff(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    conversation: asyncpg.Record,
    inbound_message: asyncpg.Record,
    policy: dict[str, Any],
    reason: str,
    reason_detail: str,
) -> dict[str, Any]:
    log.info(
        'orchestrator.handoff_triggered',
        conversation_id=str(conversation['id']),
        reason=reason,
        reason_detail=reason_detail,
        has_handoff_message=bool((policy.get('handoff_message') or '').strip()),
    )
    await conn.execute(
        """
        update app.conversations
        set status='waiting_agent', handoff_required=true, updated_at=now()
        where tenant_id=$1 and id=$2 and status != 'human_active'
        """,
        tenant_id,
        conversation['id'],
    )

    existing_handoff = await conn.fetchrow(
        """
        select id from app.handoffs
        where tenant_id=$1 and conversation_id=$2 and status='open'
        order by created_at desc limit 1
        """,
        tenant_id,
        conversation['id'],
    )
    if existing_handoff:
        handoff_id = existing_handoff['id']
    else:
        handoff_row = await conn.fetchrow(
            """
            insert into app.handoffs (tenant_id, conversation_id, reason, status)
            values ($1, $2, $3, 'open')
            returning *
            """,
            tenant_id,
            conversation['id'],
            reason,
        )
        handoff_id = handoff_row['id']

    # Send handoff_message if the policy defines one
    handoff_message_sent = False
    handoff_message_text: str = policy.get('handoff_message') or ''
    if handoff_message_text.strip():
        idempotency_key = f'handoff_msg:{inbound_message["id"]}'
        existing_event = await conn.fetchval(
            'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
            tenant_id, idempotency_key,
        )
        if not existing_event:
            trace_payload = {
                'rag_decision': 'handoff',
                'reason': reason,
                'reason_detail': reason_detail,
                'inbound_message_id': str(inbound_message['id']),
            }
            outbound_msg = await conn.fetchrow(
                """
                insert into app.messages (
                  tenant_id, conversation_id, direction, sender_actor_type,
                  body_text, message_type, status, payload
                )
                values ($1, $2, 'outbound', 'bot', $3, 'text', 'queued', $4::jsonb)
                returning *
                """,
                tenant_id,
                conversation['id'],
                handoff_message_text,
                json.dumps(trace_payload),
            )
            event_payload = {
                'message_id': str(outbound_msg['id']),
                'conversation_id': str(conversation['id']),
                'body_text': handoff_message_text,
                'channel_id': str(channel_id),
            }
            await conn.execute(
                """
                insert into app.domain_events (
                  tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
                )
                values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
                on conflict (tenant_id, idempotency_key) do nothing
                """,
                tenant_id,
                outbound_msg['id'],
                idempotency_key,
                json.dumps(event_payload),
            )
            handoff_message_sent = True

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='rag_orchestrator',
        action='bot.handoff',
        entity_type='handoff',
        entity_id=str(handoff_id),
        metadata={
            'reason': reason,
            'reason_detail': reason_detail,
            'inbound_message_id': str(inbound_message['id']),
            'handoff_message_sent': handoff_message_sent,
        },
    )

    log.info(
        'rag_orchestrator.handoff',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation['id']),
        reason=reason,
    )
    return {
        'action': 'handoff',
        'handoff_id': str(handoff_id),
        'reason': reason,
        'handoff_message_sent': handoff_message_sent,
    }
