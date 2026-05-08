import { useEffect, useMemo, useRef, useState } from 'react';

import {
  acceptConversationHandoff,
  createConversationHandoff,
  getConversation,
  listConversations,
  openConversationStream,
  releaseConversation,
  sendConversationMessage,
  startConversation,
} from '../../../services/coreApi.js';

function formatDate(value) {
  if (!value) return 'Sin fecha';
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

function statusLabel(status) {
  const labels = {
    human_active: 'Humano activo',
    human_required: 'Requiere humano',
    open: 'Bot activo',
    waiting_agent: 'Espera agente',
    waiting_user: 'Espera usuario',
  };
  return labels[status] || status;
}

function Notice({ notice }) {
  if (!notice) return null;
  return <p className={`notice ${notice.type}`}>{notice.text}</p>;
}

function deliveryLabel(message) {
  if (message.status === 'queued') return 'En cola: pendiente del worker';
  if (message.status === 'failed') return `Falló WhatsApp: ${message.error_message || message.error_code || 'sin detalle'}`;
  if (message.payload?.provider_result?.mocked) return 'Simulado local: no salió a WhatsApp';
  if (message.external_message_id) return `Aceptado por WhatsApp: ${message.external_message_id}`;
  if (message.status === 'sent') return 'Enviado al proveedor';
  return message.status;
}

export function OperationsDesk({ module, session, tenant }) {
  const [conversations, setConversations] = useState([]);
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [conversationDetail, setConversationDetail] = useState(null);
  const [messageText, setMessageText] = useState('');
  const [startForm, setStartForm] = useState({ displayName: '', initialMessage: '', phone: '' });
  const [handoffReason, setHandoffReason] = useState('manual_or_policy_handoff');
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [lastLiveRefreshAt, setLastLiveRefreshAt] = useState(null);
  const [streamStatus, setStreamStatus] = useState('disconnected');
  const messageThreadRef = useRef(null);
  const selectedConversationIdRef = useRef(null);

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId)
      || (conversationDetail?.id === selectedConversationId ? conversationDetail : null),
    [conversationDetail, conversations, selectedConversationId],
  );

  function refreshConversations(showNotice = false, silent = false) {
    if (!tenant?.id) return Promise.resolve();
    return listConversations(session, tenant.id)
      .then((items) => {
        setConversations(items);
        setSelectedConversationId((currentId) => currentId || items[0]?.id || null);
        if (showNotice) setNotice({ type: 'success', text: 'Inbox actualizado.' });
      })
      .catch((error) => {
        if (!silent) setNotice({ type: 'error', text: error.message });
      });
  }

  function refreshDetail(conversationId = selectedConversationId, silent = false) {
    if (!tenant?.id || !conversationId) {
      setConversationDetail(null);
      return Promise.resolve();
    }
    return getConversation(session, tenant.id, conversationId)
      .then(setConversationDetail)
      .catch((error) => {
        if (!silent) setNotice({ type: 'error', text: error.message });
      });
  }

  useEffect(() => {
    setSelectedConversationId(null);
    setConversationDetail(null);
    refreshConversations();
  }, [tenant?.id]);

  useEffect(() => {
    if (conversationDetail?.id === selectedConversationId) return;
    refreshDetail();
  }, [conversationDetail?.id, selectedConversationId]);

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversationId;
  }, [selectedConversationId]);

  useEffect(() => {
    if (!tenant?.id) {
      setStreamStatus('disconnected');
      return undefined;
    }
    let reconnectTimer;
    let closedByEffect = false;
    let socket;

    const connect = () => {
      socket = openConversationStream(session, tenant.id);
      setStreamStatus('connecting');

      socket.onopen = () => {
        setStreamStatus('connected');
      };

      socket.onmessage = async (event) => {
        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        if (payload.type === 'heartbeat' || payload.type === 'connected') return;
        if (payload.type !== 'conversation.changed') return;

        await refreshConversations(false, true);
        const currentConversationId = selectedConversationIdRef.current;
        const shouldRefreshDetail = currentConversationId
          && (!payload.conversation_id || payload.conversation_id === currentConversationId);
        if (shouldRefreshDetail) await refreshDetail(currentConversationId, true);
        setLastLiveRefreshAt(new Date().toISOString());
      };

      socket.onerror = () => {
        setStreamStatus('error');
      };

      socket.onclose = () => {
        if (closedByEffect) return;
        setStreamStatus('reconnecting');
        reconnectTimer = window.setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      closedByEffect = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (socket) socket.close();
      setStreamStatus('disconnected');
    };
  }, [tenant?.id, session]);

  useEffect(() => {
    const thread = messageThreadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [conversationDetail?.id, conversationDetail?.messages?.length]);

  async function runAction(action, successText) {
    if (!selectedConversationId) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await action();
      await refreshConversations();
      await refreshDetail();
      setNotice({ type: 'success', text: successText });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStartConversation(event) {
    event.preventDefault();
    const phone = startForm.phone.trim();
    const initialMessage = startForm.initialMessage.trim();
    if (!phone || !initialMessage) {
      setNotice({ type: 'error', text: 'Teléfono y mensaje inicial son obligatorios.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const conversation = await startConversation(session, tenant.id, {
        display_name: startForm.displayName.trim() || undefined,
        initial_message: initialMessage,
        phone_e164: phone,
      });
      setConversationDetail(conversation);
      setSelectedConversationId(conversation.id);
      refreshConversations();
      setStartForm({ displayName: '', initialMessage: '', phone: '' });
      setNotice({ type: 'success', text: 'Conversación iniciada y mensaje inicial encolado.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault();
    const bodyText = messageText.trim();
    if (!bodyText) {
      setNotice({ type: 'error', text: 'Escribe un mensaje antes de enviar.' });
      return;
    }
    await runAction(
      () => sendConversationMessage(session, tenant.id, selectedConversationId, { body_text: bodyText }),
      'Mensaje outbound encolado y auditado.',
    );
    setMessageText('');
  }

  return (
    <section className="module-card operations-desk">
      <div className="module-heading">
        <div>
          <p className="eyebrow">{module.label}</p>
          <h2>Inbox operativo</h2>
          <p className="hint">{module.summary}</p>
        </div>
        <div className="live-refresh-status">
          <span>Tiempo real WebSocket: {streamStatus === 'connected' ? 'conectado' : streamStatus}</span>
          {lastLiveRefreshAt
            ? <small>Último evento: {formatDate(lastLiveRefreshAt)}</small>
            : <small>Esperando cambios del servidor</small>}
          <button className="secondary-action" disabled={isBusy} onClick={() => refreshConversations(true)} type="button">
            Refrescar inbox
          </button>
        </div>
      </div>

      <Notice notice={notice} />

      <form className="start-conversation-panel" onSubmit={handleStartConversation}>
        <div>
          <strong>Iniciar conversación</strong>
          <p className="hint">Crea o reutiliza una conversación abierta y encola el primer mensaje outbound. El worker cambiará el estado queued/sent/failed según la respuesta de WhatsApp.</p>
        </div>
        <label>
          Teléfono WhatsApp E.164
          <input
            onChange={(event) => setStartForm({ ...startForm, phone: event.target.value })}
            placeholder="+573001112233"
            value={startForm.phone}
          />
        </label>
        <label>
          Nombre del contacto
          <input
            onChange={(event) => setStartForm({ ...startForm, displayName: event.target.value })}
            placeholder="Nombre visible (opcional)"
            value={startForm.displayName}
          />
        </label>
        <label className="wide">
          Mensaje inicial
          <textarea
            onChange={(event) => setStartForm({ ...startForm, initialMessage: event.target.value })}
            placeholder="Hola, te escribimos desde el equipo de atención..."
            value={startForm.initialMessage}
          />
        </label>
        <button className="primary-action" disabled={isBusy || !startForm.phone.trim() || !startForm.initialMessage.trim()} type="submit">
          Iniciar conversación
        </button>
      </form>

      <div className="operations-layout">
        <aside className="conversation-list" aria-label="Conversaciones">
          {conversations.length === 0 ? <p className="hint">No hay conversaciones para este tenant.</p> : null}
          {conversations.map((conversation) => (
            <button
              className={`conversation-card ${conversation.id === selectedConversationId ? 'active' : ''}`}
              key={conversation.id}
              onClick={() => setSelectedConversationId(conversation.id)}
              type="button"
            >
              <span>{conversation.contact_label || conversation.contact_id}</span>
              <strong>{statusLabel(conversation.status)}</strong>
              <small>{conversation.latest_message_text || 'Sin mensajes aún'}</small>
              <time>{formatDate(conversation.latest_message_at || conversation.updated_at)}</time>
            </button>
          ))}
        </aside>

        <section className="conversation-detail">
          {!selectedConversation ? (
            <div className="empty-detail">
              <h3>Selecciona una conversación</h3>
              <p className="hint">El detalle mostrará mensajes, handoffs activos y acciones operativas.</p>
            </div>
          ) : (
            <>
              <div className="detail-header">
                <div>
                  <p className="eyebrow">Conversación</p>
                  <h3>{conversationDetail?.contact_label || selectedConversation.contact_label}</h3>
                  <p className="hint">{selectedConversation.id}</p>
                </div>
                <span className={`status-pill status-${selectedConversation.status}`}>{statusLabel(selectedConversation.status)}</span>
              </div>

              <div className="handoff-panel">
                <div>
                  <strong>Handoff humano</strong>
                  <p className="hint">Crea, acepta o libera la conversación al bot con auditoría operacional.</p>
                </div>
                <input
                  aria-label="Razón de handoff"
                  onChange={(event) => setHandoffReason(event.target.value)}
                  value={handoffReason}
                />
                <div className="action-row">
                  <button
                    className="secondary-action"
                    disabled={isBusy}
                    onClick={() => runAction(
                      () => createConversationHandoff(session, tenant.id, selectedConversationId, handoffReason),
                      'Handoff creado y auditado.',
                    )}
                    type="button"
                  >
                    Crear handoff
                  </button>
                  <button
                    className="primary-action"
                    disabled={isBusy || !['human_required', 'waiting_agent', 'open'].includes(selectedConversation.status)}
                    onClick={() => runAction(
                      () => acceptConversationHandoff(session, tenant.id, selectedConversationId),
                      'Handoff aceptado; conversación tomada por agente.',
                    )}
                    type="button"
                  >
                    Tomar conversación
                  </button>
                  <button
                    className="secondary-action"
                    disabled={isBusy}
                    onClick={() => runAction(
                      () => releaseConversation(session, tenant.id, selectedConversationId),
                      'Conversación liberada al bot y auditada.',
                    )}
                    type="button"
                  >
                    Liberar al bot
                  </button>
                </div>
              </div>

              <div className="message-thread" aria-live="polite" ref={messageThreadRef}>
                {(conversationDetail?.messages || []).map((message) => (
                  <article className={`message-bubble ${message.direction}`} key={message.id}>
                    <small>{message.sender_actor_type} · {formatDate(message.created_at)} · {deliveryLabel(message)}</small>
                    <p>{message.body_text || JSON.stringify(message.payload)}</p>
                  </article>
                ))}
              </div>

              <form className="message-composer" onSubmit={handleSendMessage}>
                <label>
                  Respuesta outbound
                  <textarea
                    onChange={(event) => setMessageText(event.target.value)}
                    placeholder="Escribe la respuesta para el contacto..."
                    value={messageText}
                  />
                </label>
                <button className="primary-action" disabled={isBusy || !messageText.trim()} type="submit">
                  Enviar respuesta
                </button>
              </form>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
