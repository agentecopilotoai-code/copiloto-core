import { useEffect, useMemo, useRef, useState } from 'react';

import {
  acceptConversationHandoff,
  createConversationHandoff,
  getConversation,
  listComplaintConversations,
  listConversations,
  openConversationStream,
  releaseConversation,
  sendConversationMessage,
  startConversation,
} from '../../../../services/coreApi.js';
import { emptyMessageMedia, emptyStartForm } from '../inboxData.js';

/**
 * Data layer for the Operación · Inbox view. Owns the conversation list +
 * complaints, the inbox filter, the active-conversation selection + detail,
 * the WebSocket live-refresh stream (subscribe / backoff-reconnect / cleanup),
 * the "iniciar conversación" form, the message composer state + send, and the
 * handoff state machine (create / accept / release).
 *
 * Every `coreApi` call, the SSE/WebSocket lifecycle, the exponential-backoff
 * reconnect and the optimistic detail set are ported verbatim from the legacy
 * `OperationsDesk` — this is a structural refactor, not a rewrite.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useInboxData({ session, tenant }) {
  const [conversations, setConversations] = useState([]);
  const [complaints, setComplaints] = useState([]);
  const [inboxFilter, setInboxFilter] = useState('all');
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [conversationDetail, setConversationDetail] = useState(null);
  // UI-016.8-FU: mobile state machine. A < 480px renderizamos UNA pantalla
  // a la vez (lista hasta seleccionar; al seleccionar, detalle con back
  // button). En desktop el CSS ignora este flag y muestra side-by-side.
  // El default 'list' refleja el HTML T4 mockup: al entrar al módulo el
  // usuario aterriza en la lista, no en un detalle vacío.
  const [mobileView, setMobileView] = useState('list');
  const [messageText, setMessageText] = useState('');
  const [messageMedia, setMessageMedia] = useState(emptyMessageMedia);
  const [startForm, setStartForm] = useState(emptyStartForm);
  const [handoffReason, setHandoffReason] = useState('manual_or_policy_handoff');
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
    return Promise.all([
      listConversations(session, tenant.id),
      listComplaintConversations(session, tenant.id).catch(() => []),
    ])
      .then(([items, complaintItems]) => {
        setConversations(items);
        setComplaints(complaintItems || []);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  useEffect(() => {
    if (conversationDetail?.id === selectedConversationId) return;
    refreshDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationDetail?.id, selectedConversationId]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      setNotice({
        type: 'error',
        text: 'Para enviar imagen, video o audio agrega un media_id de Meta o una URL pública.',
      });
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
      // UI-016.8-FU (codex P2 follow-up): "Iniciar conversación" también es
      // un punto de entrada al detalle — en mobile, sin este switch, el
      // CSS `data-mobile-view='list'` ocultaría el detalle recién creado
      // y el usuario se quedaría mirando la lista sin ver su nueva
      // conversación. `selectConversation` no se reutiliza acá porque la
      // ruta de start- ya invoca su setter atómico junto al detalle
      // optimista; replicamos solo el switch a 'detail'.
      setMobileView('detail');
      refreshConversations();
      setStartForm(emptyStartForm());
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
    const isMediaMessage = messageMedia.type !== 'text';
    if (!bodyText && !isMediaMessage) {
      setNotice({ type: 'error', text: 'Escribe un mensaje antes de enviar.' });
      return;
    }
    if (isMediaMessage && !messageMedia.mediaId.trim() && !messageMedia.mediaUrl.trim()) {
      setNotice({
        type: 'error',
        text: 'Para enviar imagen, video o audio agrega un media_id de Meta o una URL pública.',
      });
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
    setMessageMedia(emptyMessageMedia());
  }

  // UI-016.8-FU: wrappers que mantienen sincronizado el state machine
  // mobile. `selectConversation` reemplaza el `setSelectedConversationId`
  // crudo desde la UI — además del id, navega a 'detail' en mobile (en
  // desktop el CSS ignora el flag, sin efecto). `showMobileList` es el
  // back navigation desde el detalle; NO limpia `selectedConversationId`
  // para que el usuario pueda volver al mismo detalle si re-selecciona.
  function selectConversation(conversationId) {
    setSelectedConversationId(conversationId);
    if (conversationId) setMobileView('detail');
  }

  function showMobileList() {
    setMobileView('list');
  }

  const actions = {
    setInboxFilter,
    setSelectedConversationId,
    selectConversation,
    setMobileView,
    showMobileList,
    setMessageText,
    setMessageMedia,
    setStartForm,
    setHandoffReason,
    setNotice,
    dismissNotice: () => setNotice(null),
    refreshConversations,
    refreshDetail,
    runAction,
    handleStartConversation,
    handleSendMessage,
    createHandoff: () => runAction(
      () => createConversationHandoff(session, tenant.id, selectedConversationId, handoffReason),
      'Handoff creado y auditado.',
    ),
    acceptHandoff: () => runAction(
      () => acceptConversationHandoff(session, tenant.id, selectedConversationId),
      'Handoff aceptado; conversación tomada por agente.',
    ),
    releaseHandoff: () => runAction(
      () => releaseConversation(session, tenant.id, selectedConversationId),
      'Conversación liberada al bot y auditada.',
    ),
  };

  return {
    state: {
      tenantId: tenant?.id,
      conversations,
      complaints,
      inboxFilter,
      selectedConversationId,
      selectedConversation,
      conversationDetail,
      messageText,
      messageMedia,
      startForm,
      handoffReason,
      isBusy,
      notice,
      lastLiveRefreshAt,
      streamStatus,
      messageThreadRef,
      mobileView,
    },
    actions,
  };
}
