import { useEffect, useMemo, useRef, useState } from 'react';

import {
  acceptConversationHandoff,
  cancelAppointment,
  createAppointment,
  createQuote,
  createResource,
  createServiceRequest,
  conversationMessageMediaUrl,
  createConversationHandoff,
  getConversation,
  getQuoteForSr,
  listAppointments,
  listConversations,
  listResources,
  listServiceRequests,
  openConversationStream,
  patchQuote,
  patchServiceRequest,
  releaseConversation,
  sendConversationMessage,
  sendQuote,
  updateAppointment,
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

function messageLabel(message) {
  const labels = {
    audio: 'Audio',
    image: 'Imagen',
    text: 'Texto',
    video: 'Video',
  };
  return labels[message.message_type] || message.message_type || 'Mensaje';
}

function mediaSource(message, session, tenantId) {
  if (
    tenantId &&
    message.id &&
    message.conversation_id &&
    message.media_id &&
    ['image', 'video', 'audio'].includes(message.message_type)
  ) {
    return conversationMessageMediaUrl(
      session,
      tenantId,
      message.conversation_id,
      message.id,
    );
  }

  return null;
}

function renderMessageContent(message, session, tenantId) {
  const source = mediaSource(message, session, tenantId);
  const text = message.body_text;

  if (message.message_type === 'image') {
    return (
      <div className="message-media">
        {source ? <img alt={text || 'Imagen de WhatsApp'} src={source} /> : <span>Imagen · media_id: {message.media_id || 'pendiente'}</span>}
        {text ? <p>{text}</p> : null}
      </div>
    );
  }

  if (message.message_type === 'video') {
    return (
      <div className="message-media">
        {source ? <video controls src={source}>Tu navegador no soporta video embebido.</video> : <span>Video · media_id: {message.media_id || 'pendiente'}</span>}
        {text ? <p>{text}</p> : null}
      </div>
    );
  }

  if (message.message_type === 'audio') {
    return (
      <div className="message-media">
        {source ? <audio controls src={source}>Tu navegador no soporta audio embebido.</audio> : <span>Audio · media_id: {message.media_id || 'pendiente'}</span>}
        {text ? <p>{text}</p> : null}
      </div>
    );
  }

  return <p>{text || JSON.stringify(message.payload)}</p>;
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
  const [messageMedia, setMessageMedia] = useState({ mediaId: '', mediaUrl: '', mimeType: '', type: 'text' });
  const [startForm, setStartForm] = useState({ displayName: '', initialMessage: '', mediaId: '', mediaUrl: '', mimeType: '', phone: '', type: 'text' });
  const [handoffReason, setHandoffReason] = useState('manual_or_policy_handoff');
  const [resources, setResources] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [resourceForm, setResourceForm] = useState({ code: '', name: '', resourceType: 'technician', verticalCode: tenant?.vertical_code || 'field_service' });
  const [appointmentForm, setAppointmentForm] = useState({ endsAt: '', notes: '', resourceId: '', serviceCode: '', startsAt: '' });
  const [rescheduleForm, setRescheduleForm] = useState({ appointmentId: '', endsAt: '', resourceId: '', startsAt: '' });
  const [serviceRequests, setServiceRequests] = useState([]);
  const [selectedSrId, setSelectedSrId] = useState(null);
  const [srQuote, setSrQuote] = useState(null);
  const [srForm, setSrForm] = useState({ serviceType: '', problemSummary: '', urgency: 'normal' });
  const [quoteItems, setQuoteItems] = useState([{ description: '', qty: 1, unit_price: 0 }]);
  const [quoteDiscount, setQuoteDiscount] = useState(0);
  const [quoteTax, setQuoteTax] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [lastLiveRefreshAt, setLastLiveRefreshAt] = useState(null);
  const [streamStatus, setStreamStatus] = useState('disconnected');
  const messageThreadRef = useRef(null);
  const selectedConversationIdRef = useRef(null);
  const streamSocketRef = useRef(null);
  const streamReconnectTimerRef = useRef(null);
  const streamReconnectAttemptRef = useRef(0);

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

  function refreshScheduleData(silent = false) {
    if (!tenant?.id) return Promise.resolve();
    return Promise.all([
      listResources(session, tenant.id),
      listAppointments(session, tenant.id),
    ]).then(([resourceItems, appointmentItems]) => {
      setResources(resourceItems);
      setAppointments(appointmentItems);
      setAppointmentForm((current) => ({ ...current, resourceId: current.resourceId || resourceItems[0]?.id || '' }));
      setRescheduleForm((current) => ({ ...current, resourceId: current.resourceId || resourceItems[0]?.id || '' }));
    }).catch((error) => {
      if (!silent) setNotice({ type: 'error', text: error.message });
    });
  }

  function refreshServiceRequests(contactId, silent = false) {
    if (!tenant?.id || !contactId) {
      setServiceRequests([]);
      setSelectedSrId(null);
      setSrQuote(null);
      return Promise.resolve();
    }
    return listServiceRequests(session, tenant.id, { contact_id: contactId })
      .then((items) => {
        setServiceRequests(items);
        setSelectedSrId((current) => current || items[0]?.id || null);
      })
      .catch((error) => {
        if (!silent) setNotice({ type: 'error', text: error.message });
      });
  }

  function refreshSrQuote(srId, silent = false) {
    if (!tenant?.id || !srId) {
      setSrQuote(null);
      return Promise.resolve();
    }
    return getQuoteForSr(session, tenant.id, srId)
      .then(setSrQuote)
      .catch((error) => {
        if (error.status === 404) {
          setSrQuote(null);
        } else if (!silent) {
          setNotice({ type: 'error', text: error.message });
        }
      });
  }

  useEffect(() => {
    setSelectedConversationId(null);
    setConversationDetail(null);
    refreshConversations();
    refreshScheduleData(true);
    setResourceForm((current) => ({ ...current, verticalCode: tenant?.vertical_code || 'field_service' }));
  }, [tenant?.id]);

  useEffect(() => {
    if (conversationDetail?.id === selectedConversationId) return;
    refreshDetail();
  }, [conversationDetail?.id, selectedConversationId]);

  useEffect(() => {
    const contactId = conversationDetail?.contact_id;
    setServiceRequests([]);
    setSelectedSrId(null);
    setSrQuote(null);
    if (contactId) refreshServiceRequests(contactId, true);
  }, [conversationDetail?.contact_id]);

  useEffect(() => {
    setSrQuote(null);
    if (selectedSrId) refreshSrQuote(selectedSrId, true);
  }, [selectedSrId]);

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversationId;
  }, [selectedConversationId]);

  useEffect(() => {
    if (!tenant?.id) {
      setStreamStatus('disconnected');
      return undefined;
    }

    let closedByEffect = false;
    const clearReconnectTimer = () => {
      if (!streamReconnectTimerRef.current) return;
      window.clearTimeout(streamReconnectTimerRef.current);
      streamReconnectTimerRef.current = null;
    };

    const scheduleReconnect = () => {
      clearReconnectTimer();
      streamReconnectAttemptRef.current += 1;
      const delayMs = Math.min(30000, 1000 * (2 ** (streamReconnectAttemptRef.current - 1)));
      setStreamStatus(`reconnecting in ${Math.round(delayMs / 1000)}s`);
      streamReconnectTimerRef.current = window.setTimeout(connect, delayMs);
    };

    const connect = () => {
      if (closedByEffect) return;
      const existingSocket = streamSocketRef.current;
      if (existingSocket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(existingSocket.readyState)) {
        return;
      }

      const socket = openConversationStream(session, tenant.id);
      streamSocketRef.current = socket;
      setStreamStatus('connecting');

      socket.onopen = () => {
        streamReconnectAttemptRef.current = 0;
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
        if (socket === streamSocketRef.current) setStreamStatus('connection error');
      };

      socket.onclose = (event) => {
        if (socket !== streamSocketRef.current) return;
        streamSocketRef.current = null;
        if (closedByEffect) return;
        if (event.code === 1008) {
          setStreamStatus(`closed: ${event.reason || 'unauthorized'}`);
          return;
        }
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      closedByEffect = true;
      clearReconnectTimer();
      const socket = streamSocketRef.current;
      streamSocketRef.current = null;
      if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) {
        socket.close(1000, 'operations_desk_unmounted');
      }
      setStreamStatus('disconnected');
    };
  }, [tenant?.id, session?.api?.baseUrl]);

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
    const isMediaMessage = startForm.type !== 'text';
    if (!phone || (!initialMessage && !isMediaMessage)) {
      setNotice({ type: 'error', text: 'Teléfono y mensaje inicial son obligatorios.' });
      return;
    }
    if (isMediaMessage && !startForm.mediaId.trim() && !startForm.mediaUrl.trim()) {
      setNotice({ type: 'error', text: 'Para enviar imagen, video o audio agrega un media_id de Meta o una URL pública.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const conversation = await startConversation(session, tenant.id, {
        display_name: startForm.displayName.trim() || undefined,
        initial_media_id: startForm.mediaId.trim() || undefined,
        initial_media_url: startForm.mediaUrl.trim() || undefined,
        initial_message: initialMessage || undefined,
        initial_message_type: startForm.type,
        initial_mime_type: startForm.mimeType.trim() || undefined,
        phone_e164: phone,
      });
      setConversationDetail(conversation);
      setSelectedConversationId(conversation.id);
      refreshConversations();
      setStartForm({ displayName: '', initialMessage: '', mediaId: '', mediaUrl: '', mimeType: '', phone: '', type: 'text' });
      setNotice({ type: 'success', text: 'Conversación iniciada y mensaje inicial encolado.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateResource(event) {
    event.preventDefault();
    if (!resourceForm.code.trim() || !resourceForm.name.trim()) {
      setNotice({ type: 'error', text: 'Código y nombre del recurso son obligatorios.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      await createResource(session, tenant.id, {
        code: resourceForm.code.trim(),
        name: resourceForm.name.trim(),
        resource_type: resourceForm.resourceType,
        vertical_code: resourceForm.verticalCode,
      });
      setResourceForm({ code: '', name: '', resourceType: 'technician', verticalCode: tenant?.vertical_code || 'field_service' });
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Recurso creado y disponible para agenda.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateAppointment(event) {
    event.preventDefault();
    if (!conversationDetail?.contact_id || !appointmentForm.resourceId || !appointmentForm.serviceCode.trim() || !appointmentForm.startsAt || !appointmentForm.endsAt) {
      setNotice({ type: 'error', text: 'Selecciona conversación, recurso, servicio e intervalo.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      await createAppointment(session, tenant.id, {
        contact_id: conversationDetail.contact_id,
        conversation_id: selectedConversationId,
        ends_at: new Date(appointmentForm.endsAt).toISOString(),
        notes: appointmentForm.notes.trim() || undefined,
        resource_id: appointmentForm.resourceId,
        service_code: appointmentForm.serviceCode.trim(),
        starts_at: new Date(appointmentForm.startsAt).toISOString(),
      });
      setAppointmentForm({ endsAt: '', notes: '', resourceId: appointmentForm.resourceId, serviceCode: '', startsAt: '' });
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Cita agendada sin conflicto de recurso.' });
    } catch (error) {
      setNotice({ type: 'error', text: typeof error.message === 'string' ? error.message : 'No fue posible agendar la cita.' });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRescheduleAppointment(event) {
    event.preventDefault();
    if (!rescheduleForm.appointmentId || !rescheduleForm.resourceId || !rescheduleForm.startsAt || !rescheduleForm.endsAt) {
      setNotice({ type: 'error', text: 'Selecciona cita, recurso y nuevo intervalo.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      await updateAppointment(session, tenant.id, rescheduleForm.appointmentId, {
        ends_at: new Date(rescheduleForm.endsAt).toISOString(),
        resource_id: rescheduleForm.resourceId,
        starts_at: new Date(rescheduleForm.startsAt).toISOString(),
      });
      setRescheduleForm({ appointmentId: '', endsAt: '', resourceId: rescheduleForm.resourceId, startsAt: '' });
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Cita reprogramada sin violar agenda.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCancelAppointment(appointmentId) {
    setIsBusy(true);
    setNotice(null);
    try {
      await cancelAppointment(session, tenant.id, appointmentId);
      await refreshScheduleData();
      setNotice({ type: 'success', text: 'Cita cancelada; el recurso queda liberado.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateServiceRequest(event) {
    event.preventDefault();
    if (!conversationDetail?.contact_id || !srForm.serviceType.trim()) {
      setNotice({ type: 'error', text: 'Tipo de servicio es obligatorio.' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      const sr = await createServiceRequest(session, tenant.id, {
        contact_id: conversationDetail.contact_id,
        conversation_id: selectedConversationId,
        vertical_code: tenant.vertical_code || 'field_service',
        service_type: srForm.serviceType.trim(),
        problem_summary: srForm.problemSummary.trim() || undefined,
        urgency: srForm.urgency,
      });
      setSrForm({ serviceType: '', problemSummary: '', urgency: 'normal' });
      await refreshServiceRequests(conversationDetail.contact_id);
      setSelectedSrId(sr.id);
      setNotice({ type: 'success', text: 'Solicitud de servicio registrada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handlePatchSrStatus(srId, newStatus) {
    setIsBusy(true);
    setNotice(null);
    try {
      await patchServiceRequest(session, tenant.id, srId, { status: newStatus });
      await refreshServiceRequests(conversationDetail?.contact_id);
      setNotice({ type: 'success', text: `Solicitud actualizada a "${newStatus}".` });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function computeQuoteTotals() {
    const subtotal = quoteItems.reduce((acc, item) => acc + (parseFloat(item.qty) || 0) * (parseFloat(item.unit_price) || 0), 0);
    const grandTotal = subtotal - (parseFloat(quoteDiscount) || 0) + (parseFloat(quoteTax) || 0);
    return { subtotal, grandTotal };
  }

  async function handleCreateQuote(event) {
    event.preventDefault();
    if (!selectedSrId) return;
    const validItems = quoteItems.filter((item) => item.description.trim());
    setIsBusy(true);
    setNotice(null);
    try {
      const { subtotal: _s, grandTotal: _g, ...rest } = computeQuoteTotals();
      void _s; void _g; void rest;
      await createQuote(session, tenant.id, selectedSrId, {
        line_items: validItems.map((item) => ({
          description: item.description.trim(),
          qty: parseFloat(item.qty) || 1,
          unit_price: parseFloat(item.unit_price) || 0,
        })),
        discount_total: parseFloat(quoteDiscount) || 0,
        tax_total: parseFloat(quoteTax) || 0,
      });
      await refreshSrQuote(selectedSrId);
      await refreshServiceRequests(conversationDetail?.contact_id, true);
      setNotice({ type: 'success', text: 'Cotización creada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSendQuote() {
    if (!srQuote?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await sendQuote(session, tenant.id, srQuote.id);
      await refreshSrQuote(selectedSrId);
      setNotice({ type: 'success', text: 'Cotización enviada al contacto por WhatsApp.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleUpdateQuoteStatus(newStatus) {
    if (!srQuote?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await patchQuote(session, tenant.id, srQuote.id, { status: newStatus });
      await refreshSrQuote(selectedSrId);
      setNotice({ type: 'success', text: `Cotización actualizada a "${newStatus}".` });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function addQuoteItem() {
    setQuoteItems((current) => [...current, { description: '', qty: 1, unit_price: 0 }]);
  }

  function removeQuoteItem(index) {
    setQuoteItems((current) => current.filter((_, i) => i !== index));
  }

  function updateQuoteItem(index, field, value) {
    setQuoteItems((current) => current.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  }

  async function handleSendMessage(event) {
    event.preventDefault();
    const bodyText = messageText.trim();
    const isMediaMessage = messageMedia.type !== 'text';
    if (!bodyText && !isMediaMessage) {
      setNotice({ type: 'error', text: 'Escribe un mensaje antes de enviar.' });
      return;
    }
    if (isMediaMessage && !messageMedia.mediaId.trim() && !messageMedia.mediaUrl.trim()) {
      setNotice({ type: 'error', text: 'Para enviar imagen, video o audio agrega un media_id de Meta o una URL pública.' });
      return;
    }
    await runAction(
      () => sendConversationMessage(session, tenant.id, selectedConversationId, {
        body_text: bodyText || undefined,
        media_id: messageMedia.mediaId.trim() || undefined,
        message_type: messageMedia.type,
        mime_type: messageMedia.mimeType.trim() || undefined,
        payload: messageMedia.mediaUrl.trim() ? { media_url: messageMedia.mediaUrl.trim() } : {},
      }),
      'Mensaje outbound encolado y auditado.',
    );
    setMessageText('');
    setMessageMedia({ mediaId: '', mediaUrl: '', mimeType: '', type: 'text' });
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
        <label>
          Tipo de mensaje
          <select
            onChange={(event) => setStartForm({ ...startForm, type: event.target.value })}
            value={startForm.type}
          >
            <option value="text">Texto</option>
            <option value="image">Imagen</option>
            <option value="video">Video</option>
            <option value="audio">Audio</option>
          </select>
        </label>
        <label>
          MIME type
          <input
            onChange={(event) => setStartForm({ ...startForm, mimeType: event.target.value })}
            placeholder="image/jpeg, video/mp4, audio/ogg"
            value={startForm.mimeType}
          />
        </label>
        <label>
          Media ID Meta
          <input
            onChange={(event) => setStartForm({ ...startForm, mediaId: event.target.value })}
            placeholder="ID del media subido a WhatsApp"
            value={startForm.mediaId}
          />
        </label>
        <label>
          URL pública media
          <input
            onChange={(event) => setStartForm({ ...startForm, mediaUrl: event.target.value })}
            placeholder="https://..."
            value={startForm.mediaUrl}
          />
        </label>
        <label className="wide">
          Mensaje inicial / caption
          <textarea
            onChange={(event) => setStartForm({ ...startForm, initialMessage: event.target.value })}
            placeholder="Texto para mensajes de texto o caption para imagen/video..."
            value={startForm.initialMessage}
          />
        </label>
        <button className="primary-action" disabled={isBusy || !startForm.phone.trim() || (startForm.type === 'text' && !startForm.initialMessage.trim())} type="submit">
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

              <div className="schedule-panel">
                <div>
                  <strong>Recursos y agenda</strong>
                  <p className="hint">Configura recursos, agenda citas para el contacto seleccionado y reprograma/cancela sin solapar reservas activas.</p>
                </div>

                <form className="schedule-form" onSubmit={handleCreateResource}>
                  <label>
                    Código recurso
                    <input
                      onChange={(event) => setResourceForm({ ...resourceForm, code: event.target.value })}
                      placeholder="TEC-01"
                      value={resourceForm.code}
                    />
                  </label>
                  <label>
                    Nombre recurso
                    <input
                      onChange={(event) => setResourceForm({ ...resourceForm, name: event.target.value })}
                      placeholder="Técnico / silla / sala"
                      value={resourceForm.name}
                    />
                  </label>
                  <label>
                    Tipo
                    <select
                      onChange={(event) => setResourceForm({ ...resourceForm, resourceType: event.target.value })}
                      value={resourceForm.resourceType}
                    >
                      <option value="technician">Técnico</option>
                      <option value="chair">Silla</option>
                      <option value="stylist">Estilista</option>
                      <option value="groomer">Groomer</option>
                      <option value="room">Sala</option>
                      <option value="vehicle">Vehículo</option>
                    </select>
                  </label>
                  <button className="secondary-action" disabled={isBusy} type="submit">Crear recurso</button>
                </form>

                <form className="schedule-form" onSubmit={handleCreateAppointment}>
                  <label>
                    Recurso
                    <select
                      onChange={(event) => setAppointmentForm({ ...appointmentForm, resourceId: event.target.value })}
                      value={appointmentForm.resourceId}
                    >
                      <option value="">Selecciona recurso</option>
                      {resources.filter((resource) => resource.is_active).map((resource) => (
                        <option key={resource.id} value={resource.id}>{resource.name} ({resource.code})</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Servicio
                    <input
                      onChange={(event) => setAppointmentForm({ ...appointmentForm, serviceCode: event.target.value })}
                      placeholder="diagnostico / corte / baño"
                      value={appointmentForm.serviceCode}
                    />
                  </label>
                  <label>
                    Inicio
                    <input
                      onChange={(event) => setAppointmentForm({ ...appointmentForm, startsAt: event.target.value })}
                      type="datetime-local"
                      value={appointmentForm.startsAt}
                    />
                  </label>
                  <label>
                    Fin
                    <input
                      onChange={(event) => setAppointmentForm({ ...appointmentForm, endsAt: event.target.value })}
                      type="datetime-local"
                      value={appointmentForm.endsAt}
                    />
                  </label>
                  <label>
                    Notas
                    <input
                      onChange={(event) => setAppointmentForm({ ...appointmentForm, notes: event.target.value })}
                      placeholder="Notas internas"
                      value={appointmentForm.notes}
                    />
                  </label>
                  <button className="primary-action" disabled={isBusy || !conversationDetail?.contact_id} type="submit">Crear cita</button>
                </form>

                <form className="schedule-form" onSubmit={handleRescheduleAppointment}>
                  <label>
                    Cita
                    <select
                      onChange={(event) => setRescheduleForm({ ...rescheduleForm, appointmentId: event.target.value })}
                      value={rescheduleForm.appointmentId}
                    >
                      <option value="">Selecciona cita activa</option>
                      {appointments.filter((appointment) => ['scheduled', 'confirmed'].includes(appointment.status)).map((appointment) => (
                        <option key={appointment.id} value={appointment.id}>{formatDate(appointment.starts_at)} · {appointment.resource_name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Nuevo recurso
                    <select
                      onChange={(event) => setRescheduleForm({ ...rescheduleForm, resourceId: event.target.value })}
                      value={rescheduleForm.resourceId}
                    >
                      <option value="">Selecciona recurso</option>
                      {resources.filter((resource) => resource.is_active).map((resource) => (
                        <option key={resource.id} value={resource.id}>{resource.name} ({resource.code})</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Nuevo inicio
                    <input
                      onChange={(event) => setRescheduleForm({ ...rescheduleForm, startsAt: event.target.value })}
                      type="datetime-local"
                      value={rescheduleForm.startsAt}
                    />
                  </label>
                  <label>
                    Nuevo fin
                    <input
                      onChange={(event) => setRescheduleForm({ ...rescheduleForm, endsAt: event.target.value })}
                      type="datetime-local"
                      value={rescheduleForm.endsAt}
                    />
                  </label>
                  <button className="secondary-action" disabled={isBusy} type="submit">Reprogramar</button>
                </form>

                <div className="appointment-list">
                  {appointments.slice(0, 8).map((appointment) => (
                    <article key={appointment.id}>
                      <strong>{formatDate(appointment.starts_at)} — {formatDate(appointment.ends_at)}</strong>
                      <small>{appointment.resource_name} · {appointment.service_code} · {appointment.status}</small>
                      {appointment.status !== 'cancelled' && (
                        <button className="secondary-action" disabled={isBusy} onClick={() => handleCancelAppointment(appointment.id)} type="button">Cancelar</button>
                      )}
                    </article>
                  ))}
                </div>
              </div>

              <div className="service-requests-panel">
                <div>
                  <strong>Solicitudes de servicio y cotizaciones</strong>
                  <p className="hint">Registra solicitudes de servicio del contacto y genera cotizaciones orientativas enviables por WhatsApp.</p>
                </div>

                <form className="schedule-form" onSubmit={handleCreateServiceRequest}>
                  <label>
                    Tipo de servicio
                    <input
                      onChange={(event) => setSrForm({ ...srForm, serviceType: event.target.value })}
                      placeholder="diagnostico / corte / baño / instalacion"
                      value={srForm.serviceType}
                    />
                  </label>
                  <label>
                    Urgencia
                    <select
                      onChange={(event) => setSrForm({ ...srForm, urgency: event.target.value })}
                      value={srForm.urgency}
                    >
                      <option value="low">Baja</option>
                      <option value="normal">Normal</option>
                      <option value="high">Alta</option>
                      <option value="emergency">Emergencia</option>
                    </select>
                  </label>
                  <label className="wide">
                    Descripción del problema
                    <textarea
                      onChange={(event) => setSrForm({ ...srForm, problemSummary: event.target.value })}
                      placeholder="Descripción breve de la solicitud..."
                      value={srForm.problemSummary}
                    />
                  </label>
                  <button className="secondary-action" disabled={isBusy || !conversationDetail?.contact_id || !srForm.serviceType.trim()} type="submit">
                    Crear solicitud
                  </button>
                </form>

                {serviceRequests.length > 0 && (
                  <div className="sr-list">
                    {serviceRequests.map((sr) => (
                      <button
                        className={`sr-card ${sr.id === selectedSrId ? 'active' : ''}`}
                        key={sr.id}
                        onClick={() => setSelectedSrId(sr.id)}
                        type="button"
                      >
                        <span>{sr.service_type}</span>
                        <small>{sr.vertical_code} · {sr.urgency} · <strong>{sr.status}</strong></small>
                        {sr.problem_summary && <small>{sr.problem_summary}</small>}
                      </button>
                    ))}
                  </div>
                )}

                {selectedSrId && (
                  <div className="sr-detail">
                    <div className="action-row">
                      {['open', 'qualified'].includes(serviceRequests.find((sr) => sr.id === selectedSrId)?.status) && (
                        <button className="secondary-action" disabled={isBusy} onClick={() => handlePatchSrStatus(selectedSrId, 'cancelled')} type="button">
                          Cancelar solicitud
                        </button>
                      )}
                      {serviceRequests.find((sr) => sr.id === selectedSrId)?.status === 'open' && (
                        <button className="secondary-action" disabled={isBusy} onClick={() => handlePatchSrStatus(selectedSrId, 'qualified')} type="button">
                          Marcar calificada
                        </button>
                      )}
                    </div>

                    {!srQuote ? (
                      <form className="quote-form" onSubmit={handleCreateQuote}>
                        <strong>Nueva cotización</strong>
                        {quoteItems.map((item, index) => (
                          <div className="quote-item-row" key={index}>
                            <input
                              onChange={(event) => updateQuoteItem(index, 'description', event.target.value)}
                              placeholder="Descripción del ítem"
                              value={item.description}
                            />
                            <input
                              min="0.01"
                              onChange={(event) => updateQuoteItem(index, 'qty', event.target.value)}
                              placeholder="Cant."
                              step="0.01"
                              type="number"
                              value={item.qty}
                            />
                            <input
                              min="0"
                              onChange={(event) => updateQuoteItem(index, 'unit_price', event.target.value)}
                              placeholder="Precio unit."
                              step="0.01"
                              type="number"
                              value={item.unit_price}
                            />
                            <span className="item-total">
                              {((parseFloat(item.qty) || 0) * (parseFloat(item.unit_price) || 0)).toLocaleString('es-CO')}
                            </span>
                            {quoteItems.length > 1 && (
                              <button className="secondary-action" onClick={() => removeQuoteItem(index)} type="button">✕</button>
                            )}
                          </div>
                        ))}
                        <button className="secondary-action" onClick={addQuoteItem} type="button">+ Agregar ítem</button>
                        <div className="quote-totals-row">
                          <label>
                            Descuento
                            <input
                              min="0"
                              onChange={(event) => setQuoteDiscount(event.target.value)}
                              step="0.01"
                              type="number"
                              value={quoteDiscount}
                            />
                          </label>
                          <label>
                            Impuestos
                            <input
                              min="0"
                              onChange={(event) => setQuoteTax(event.target.value)}
                              step="0.01"
                              type="number"
                              value={quoteTax}
                            />
                          </label>
                          <div className="grand-total">
                            Total: <strong>{computeQuoteTotals().grandTotal.toLocaleString('es-CO')} COP</strong>
                          </div>
                        </div>
                        <button className="primary-action" disabled={isBusy || !quoteItems.some((item) => item.description.trim())} type="submit">
                          Crear cotización
                        </button>
                      </form>
                    ) : (
                      <div className="quote-detail">
                        <div className="quote-header">
                          <strong>Cotización</strong>
                          <span className={`status-pill status-${srQuote.status}`}>{srQuote.status}</span>
                        </div>
                        <table className="quote-items-table">
                          <thead>
                            <tr><th>Descripción</th><th>Cant.</th><th>P. Unit.</th><th>Total</th></tr>
                          </thead>
                          <tbody>
                            {(Array.isArray(srQuote.line_items) ? srQuote.line_items : JSON.parse(srQuote.line_items || '[]')).map((item, index) => (
                              <tr key={index}>
                                <td>{item.description}</td>
                                <td>{item.qty}</td>
                                <td>{Number(item.unit_price).toLocaleString('es-CO')}</td>
                                <td>{(item.qty * item.unit_price).toLocaleString('es-CO')}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr><td colSpan="3">Subtotal</td><td>{Number(srQuote.subtotal).toLocaleString('es-CO')}</td></tr>
                            <tr><td colSpan="3">Descuento</td><td>-{Number(srQuote.discount_total).toLocaleString('es-CO')}</td></tr>
                            <tr><td colSpan="3">Impuestos</td><td>+{Number(srQuote.tax_total).toLocaleString('es-CO')}</td></tr>
                            <tr className="total-row"><td colSpan="3"><strong>Total</strong></td><td><strong>{Number(srQuote.grand_total).toLocaleString('es-CO')} {srQuote.currency}</strong></td></tr>
                          </tfoot>
                        </table>
                        {srQuote.valid_until && (
                          <small>Válida hasta: {formatDate(srQuote.valid_until)}</small>
                        )}
                        <div className="action-row">
                          {srQuote.status === 'draft' && (
                            <button className="primary-action" disabled={isBusy} onClick={handleSendQuote} type="button">
                              Enviar por WhatsApp
                            </button>
                          )}
                          {srQuote.status === 'sent' && (
                            <button className="secondary-action" disabled={isBusy} onClick={() => handleUpdateQuoteStatus('accepted')} type="button">
                              Marcar aceptada
                            </button>
                          )}
                          {['sent', 'draft'].includes(srQuote.status) && (
                            <button className="secondary-action" disabled={isBusy} onClick={() => handleUpdateQuoteStatus('rejected')} type="button">
                              Marcar rechazada
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="message-thread" aria-live="polite" ref={messageThreadRef}>
                {(conversationDetail?.messages || []).map((message) => (
                  <article className={`message-bubble ${message.direction}`} key={message.id}>
                    <small>
                      {message.sender_actor_type} · {messageLabel(message)} · {formatDate(message.created_at)} · {deliveryLabel(message)}
                    </small>
                    {renderMessageContent(message, session, tenant?.id)}
                  </article>
                ))}
              </div>

              <form className="message-composer" onSubmit={handleSendMessage}>
                <label>
                  Tipo de respuesta
                  <select
                    onChange={(event) => setMessageMedia({ ...messageMedia, type: event.target.value })}
                    value={messageMedia.type}
                  >
                    <option value="text">Texto</option>
                    <option value="image">Imagen</option>
                    <option value="video">Video</option>
                    <option value="audio">Audio</option>
                  </select>
                </label>
                <label>
                  Media ID Meta
                  <input
                    onChange={(event) => setMessageMedia({ ...messageMedia, mediaId: event.target.value })}
                    placeholder="ID del media subido a WhatsApp"
                    value={messageMedia.mediaId}
                  />
                </label>
                <label>
                  URL pública media
                  <input
                    onChange={(event) => setMessageMedia({ ...messageMedia, mediaUrl: event.target.value })}
                    placeholder="https://..."
                    value={messageMedia.mediaUrl}
                  />
                </label>
                <label>
                  MIME type
                  <input
                    onChange={(event) => setMessageMedia({ ...messageMedia, mimeType: event.target.value })}
                    placeholder="image/jpeg, video/mp4, audio/ogg"
                    value={messageMedia.mimeType}
                  />
                </label>
                <label>
                  Respuesta outbound / caption
                  <textarea
                    onChange={(event) => setMessageText(event.target.value)}
                    placeholder="Escribe texto o caption para imagen/video..."
                    value={messageText}
                  />
                </label>
                <button className="primary-action" disabled={isBusy || (messageMedia.type === 'text' && !messageText.trim())} type="submit">
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
