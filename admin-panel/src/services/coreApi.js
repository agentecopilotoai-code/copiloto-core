import { adminPath } from './adminSession.js';

function buildHeaders(session, tenantId, body) {
  const headers = {
    accept: 'application/json',
  };

  if (body !== undefined) {
    headers['content-type'] = 'application/json';
  }

  if (session?.accessToken) {
    headers.authorization = `Bearer ${session.accessToken}`;
  }

  if (tenantId) {
    headers['X-Tenant-Id'] = tenantId;
  }

  return headers;
}


function coreWebSocketPath(session, path, params = {}) {
  const baseUrl = session?.api?.baseUrl || '/admin/api/core/v1';
  const httpUrl = new URL(adminPath(`${baseUrl}${path}`), window.location.href);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) httpUrl.searchParams.set(key, value);
  });
  httpUrl.protocol = httpUrl.protocol === 'https:' ? 'wss:' : 'ws:';
  return httpUrl.toString();
}

function coreApiPath(session, path) {
  const baseUrl = session?.api?.baseUrl || '/admin/api/core/v1';
  return adminPath(`${baseUrl}${path}`);
}

async function request(path, { body, method = 'GET', session, tenantId } = {}) {
  const response = await fetch(coreApiPath(session, path), {
    credentials: 'include',
    method,
    headers: buildHeaders(session, tenantId, body),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    let rawDetail = null;
    try {
      const payload = await response.json();
      rawDetail = payload?.detail ?? payload ?? null;
      if (typeof payload?.detail === 'string') {
        detail = payload.detail;
      } else if (payload?.detail && typeof payload.detail === 'object') {
        // UI-016.1-FU: backend may return a structured detail (e.g. 409
        // with {message, reasons, checks}). Surface the human message in
        // `error.message`, keep the full object on `error.detail`.
        detail = payload.detail.message || JSON.stringify(payload.detail);
      } else {
        detail = JSON.stringify(payload);
      }
    } catch {
      detail = response.statusText || detail;
    }
    const error = new Error(detail);
    error.status = response.status;
    error.detail = rawDetail;
    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function uploadMultipart(path, { formData, method = 'POST', session, tenantId } = {}) {
  const response = await fetch(coreApiPath(session, path), {
    credentials: 'include',
    method,
    headers: buildHeaders(session, tenantId),
    body: formData,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      detail = response.statusText || detail;
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

export function createTenant(session, payload) {
  return request('/tenant-signup', { method: 'POST', session, body: payload });
}

export function listFleetTenants(session, { status, country, vertical, search, limit, offset } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (country) params.set('country', country);
  if (vertical) params.set('vertical', vertical);
  if (search) params.set('search', search);
  if (limit !== undefined && limit !== null) params.set('limit', String(limit));
  if (offset !== undefined && offset !== null) params.set('offset', String(offset));
  const qs = params.toString();
  return request(`/tenants${qs ? `?${qs}` : ''}`, { session });
}

// PLATFORM-MODULES-EXPAND ──────────────────────────────────────────────────
// Lista cruzada de `app.tenant_modules`. El backend (TASK-INFLU-019) expone
// el endpoint genérico con filtros server-side por `module`, `enabled` y
// `tenant_search` (busca en slug + name, like-case-insensitive).
// Para uso por tenant exacto (el caso del FleetDrawer) el caller pasa el
// `tenantSlug` y luego filtra client-side por `tenant_id` exacto — el
// backend no soporta filtro por id, así que el slug es la ruta más estrecha
// disponible (puede traer matches parciales).
export function listTenantModules(session, { module, enabled, tenantSearch } = {}) {
  const params = new URLSearchParams();
  if (module) params.set('module', module);
  if (enabled !== undefined && enabled !== null) params.set('enabled', String(enabled));
  if (tenantSearch) params.set('tenant_search', tenantSearch);
  const qs = params.toString();
  return request(`/platform/tenant-modules${qs ? `?${qs}` : ''}`, { session });
}

// Activa o desactiva un módulo opt-in para un tenant.
// Backend valida `require_platform_owner` + MFA y deja audit
// `platform.tenant_module.activated|deactivated`.
export function updateTenantModule(session, tenantId, moduleCode, { enabled, plan, notes } = {}) {
  return request(`/platform/tenant-modules/${tenantId}/${moduleCode}`, {
    method: 'PATCH',
    session,
    body: {
      enabled: Boolean(enabled),
      plan: plan ?? null,
      notes: notes ?? null,
    },
  });
}

// Catálogo cross-modalidad de proveedores IA — recurso transversal de
// plataforma usado por Influencer, Gestión Documental y futuros módulos.
// Backend resuelve `platform_admin_router` + MFA. La response nunca
// incluye `ciphertext` ni `secret_value`: solo `hint` (últimos 4 chars).
export function listAIProviders(session) {
  return request('/platform/ai-providers', { session });
}

// Actualiza la config de una modalidad (`llm`/`image`/`video`/`tts`/`stt`).
// Si `secret_value` viene presente, el backend rota la key — guarda solo el
// hint en DB y emite audit `platform.ai_provider_updated` con
// `secret_rotated=true`. Sin `secret_value`, el PATCH solo cambia
// `provider`/`model`/`params`.
export function updateAIProvider(session, modality, payload) {
  return request(`/platform/ai-providers/${modality}`, {
    method: 'PATCH',
    session,
    body: payload,
  });
}

// Smoke test contra el provider configurado. El backend resuelve el API key
// del env var `AI_PROVIDER_SECRET_<hint>` (con fallback retro-compat al
// nombre histórico `INFLUENCER_SECRET_<hint>`), instancia el adapter,
// llama al modelo y devuelve el output uniforme. Cuerpo del payload depende
// de la modalidad — ver `aiProvidersData.buildTestPayload`. Errores del
// provider (rate-limit, content-filter, etc.) llegan como 200 con `ok:false`
// y `error_class` para que la UI muestre el detalle granular.
export function testAIProvider(session, modality, body) {
  return request(`/platform/ai-providers/${modality}/test`, {
    method: 'POST',
    session,
    body,
  });
}

export function getTenant(session, tenantId) {
  return request(`/tenants/${tenantId}`, { session, tenantId });
}

export function getSystemHealth(session) {
  return request('/platform/metrics/health', { session });
}

export function getPlatformBillingMrr(session) {
  return request('/platform/billing/mrr', { session });
}

export function getPlatformIncidents(session, { status, kind, limit } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (kind) params.set('kind', kind);
  if (limit !== undefined && limit !== null) params.set('limit', String(limit));
  const qs = params.toString();
  return request(`/platform/incidents${qs ? `?${qs}` : ''}`, { session });
}

export function getPlatformOutboundDlq(session, { windowMinutes, tenantId, errorCode } = {}) {
  const params = new URLSearchParams();
  if (windowMinutes !== undefined && windowMinutes !== null) {
    params.set('window_minutes', String(windowMinutes));
  }
  if (tenantId) params.set('tenant_id', tenantId);
  if (errorCode) params.set('error_code', errorCode);
  const qs = params.toString();
  return request(`/platform/outbound-dlq${qs ? `?${qs}` : ''}`, { session });
}

export function retryPlatformOutboundDlq(session, payload) {
  return request('/platform/outbound-dlq/retry', { method: 'POST', session, body: payload });
}

export function getPlatformRunbooks(session) {
  return request('/platform/runbooks', { session });
}

export function getPlatformRunbook(session, slug) {
  return request(`/platform/runbooks/${encodeURIComponent(slug)}`, { session });
}

export function getPlatformFeatureFlags(session) {
  return request('/platform/feature-flags', { session });
}

export function updateTenant(session, tenantId, payload) {
  return request(`/tenants/${tenantId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function patchTenantStatus(session, tenantId, status, reason) {
  return request(`/tenants/${tenantId}/status`, {
    method: 'PATCH',
    session,
    tenantId,
    body: { status, reason },
  });
}

export function getTenantSettings(session, tenantId) {
  return request(`/tenants/${tenantId}/settings`, { session, tenantId });
}

export function updateTenantSettings(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/settings`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

// UI-012-FU: upload a tenant brand logo.
// The backend reuses ``store_media_file`` (kind=image) which enforces the
// MIME allowlist (png/jpeg/webp) and the size cap; this helper just
// packages the file as multipart/form-data so ``request`` is bypassed
// (it forces application/json).
export function uploadTenantBrandLogo(session, tenantId, file) {
  const formData = new FormData();
  formData.append('file', file);
  return uploadMultipart(`/tenants/${tenantId}/branding/logo`, {
    formData,
    method: 'POST',
    session,
    tenantId,
  });
}

/**
 * BUG-177: el proxy `/v1/tenants/{id}/media/{asset_id}/content` requiere
 * `Authorization: Bearer <token>` (vive en `tenant_ops_router` que pasa por
 * `authenticate_request`). Un `<img src="/v1/...">` no manda headers, así
 * que el browser recibe 401 → imagen rota. Este helper fetchea con las
 * mismas credenciales que `request()` (Bearer + X-Tenant-Id), recibe un
 * Blob y devuelve un object URL que el caller asigna a `<img src>`.
 *
 * El caller DEBE revocar el object URL al desmontar:
 *
 *   const blobUrl = await fetchTenantMediaBlobUrl(session, tenantId, path);
 *   try { ... } finally { URL.revokeObjectURL(blobUrl); }
 *
 * @param {object} session — admin session
 * @param {string} tenantId — uuid del tenant (para X-Tenant-Id)
 * @param {string} mediaPath — path absoluto tipo
 *   `/v1/tenants/<tenant_id>/media/<asset_id>/content` (lo que el upload
 *   persiste hoy en `tenant_settings.brand_logo_url`).
 * @returns {Promise<string>} object URL (`blob:`) listo para `<img src>`.
 */
export async function fetchTenantMediaBlobUrl(session, tenantId, mediaPath) {
  // mediaPath llega como `/v1/tenants/.../media/.../content` desde la API,
  // pero `coreApiPath` ya monta `/admin/api/core/v1` como prefijo.
  // Stripeamos el `/v1` para no duplicarlo.
  const stripped = mediaPath.replace(/^\/v1/, '');
  const response = await fetch(coreApiPath(session, stripped), {
    credentials: 'include',
    method: 'GET',
    headers: buildHeaders(session, tenantId, undefined),
  });
  if (!response.ok) {
    throw new Error(`media fetch failed: HTTP ${response.status}`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export function listRetentionPolicies(session, tenantId) {
  return request(`/tenants/${tenantId}/retention/policies`, { session, tenantId });
}

export function updateRetentionPolicies(session, tenantId, policies) {
  return request(`/tenants/${tenantId}/retention/policies`, {
    method: 'PUT',
    session,
    tenantId,
    body: { policies },
  });
}

export function getRetentionPreview(session, tenantId) {
  return request(`/tenants/${tenantId}/retention/preview`, { session, tenantId });
}

// TASK-0067: digest subscriptions (resumen periódico al manager).
export function listDigestSubscriptions(session, tenantId) {
  return request(`/tenants/${tenantId}/digest/subscriptions`, { session, tenantId });
}

export function createDigestSubscription(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/digest/subscriptions`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateDigestSubscription(session, tenantId, subscriptionId, payload) {
  return request(`/tenants/${tenantId}/digest/subscriptions/${subscriptionId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deleteDigestSubscription(session, tenantId, subscriptionId) {
  return request(`/tenants/${tenantId}/digest/subscriptions/${subscriptionId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}


// TASK-0069: onboarding self-service wizard.
export function getTenantOnboarding(session, tenantId) {
  return request(`/tenants/${tenantId}/onboarding`, { session, tenantId });
}

export function verifyOnboardingStep(session, tenantId, step) {
  return request(`/tenants/${tenantId}/onboarding/steps/${step}/verify`, {
    method: 'POST',
    session,
    tenantId,
    body: {},
  });
}

export function completeOnboardingStep(session, tenantId, step, evidence = {}) {
  return request(`/tenants/${tenantId}/onboarding/steps/${step}/complete`, {
    method: 'POST',
    session,
    tenantId,
    body: { evidence },
  });
}

export function recordOnboardingTestMessageSent(session, tenantId, waId) {
  return request(`/tenants/${tenantId}/onboarding/steps/7/send-test`, {
    method: 'POST',
    session,
    tenantId,
    body: { wa_id: waId },
  });
}


export function getTenantReadiness(session, tenantId, options = {}) {
  const params = new URLSearchParams();
  if (options.smokeQuestion) params.set('smoke_question', options.smokeQuestion);
  if (options.retrievalMinScore !== undefined && options.retrievalMinScore !== '') {
    params.set('retrieval_min_score', options.retrievalMinScore);
  }
  const query = params.toString();
  return request(`/tenants/${tenantId}/readiness${query ? `?${query}` : ''}`, { session, tenantId });
}

// UI-016.1-FU: marca el tenant como live en producción. Llama al endpoint
// `POST /tenants/{id}/go-live` que valida la readiness checklist y devuelve
// 409 si algún check sigue pendiente. Idempotente — re-clicks devuelven el
// reporte actual sin sobrescribir el go_live_at original.
export function markTenantLive(session, tenantId, reason) {
  const body = reason ? { reason } : {};
  return request(`/tenants/${tenantId}/go-live`, {
    method: 'POST',
    session,
    tenantId,
    body,
  });
}

export function listAuditLogs(session, tenantId) {
  return request('/audit-logs', { session, tenantId });
}

export function listAuditLogsFiltered(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/audit-logs${query ? `?${query}` : ''}`, { session, tenantId });
}

async function downloadAuthenticated(session, tenantId, path, filename) {
  const response = await fetch(coreApiPath(session, path), {
    credentials: 'include',
    headers: buildHeaders(session, tenantId),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch { /* ignore */ }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function exportAuditLogs(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return downloadAuthenticated(
    session,
    tenantId,
    `/audit-logs/export${query ? `?${query}` : ''}`,
    `audit-logs-${tenantId}.csv`,
  );
}

export function suppressContact(session, tenantId, contactId) {
  return request(`/contacts/${contactId}/suppress`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function exportTenantData(session, tenantId) {
  return downloadAuthenticated(
    session,
    tenantId,
    `/tenants/${tenantId}/data-export`,
    `tenant-data-${tenantId}.json`,
  );
}

export function listMyTenants(session) {
  return request('/me/tenants', { session });
}

// UI-016.7-FU: per-user preferences endpoints. The backend resolves the
// user_id from the JWT, so there is no path parameter for the subject —
// these helpers cannot be used to read or edit another user's data.
export function getMyProfile(session) {
  return request('/me/profile', { session });
}

export function patchMyProfile(session, payload) {
  return request('/me/profile', { method: 'PATCH', session, body: payload });
}

export function getMyPreferences(session) {
  return request('/me/preferences', { session });
}

export function patchMyPreferences(session, payload) {
  return request('/me/preferences', { method: 'PATCH', session, body: payload });
}

export function getMyNotifications(session) {
  return request('/me/notifications', { session });
}

export function patchMyNotifications(session, notificationMatrix) {
  return request('/me/notifications', {
    method: 'PATCH',
    session,
    body: { notification_matrix: notificationMatrix },
  });
}

// UI-016.7-FU stub: backend returns only the current session until
// UI-016.7-FU-SESSIONS lands a server-side session store.
export function listMySessions(session) {
  return request('/me/sessions', { session });
}

export function revokeMySession(session, sessionId) {
  return request(`/me/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    session,
  });
}

// BUG-008 — opt-in temporal del support_mode para un tenant. El backend
// emite cookie HTTP-only firmado scoped al `tenant_id`; subsiguientes
// requests con `X-Tenant-Id=tenant_id` reciben `support_mode=true`
// automáticamente. El cookie expira a las `ttl_seconds` o cuando el caller
// invoca `deactivateSupportModeForTenant`.
export function activateSupportModeForTenant(session, tenantId, { justification } = {}) {
  return request(`/me/support-mode/${encodeURIComponent(tenantId)}`, {
    method: 'POST',
    session,
    body: justification ? { justification } : {},
  });
}

export function deactivateSupportModeForTenant(session, tenantId) {
  return request(`/me/support-mode/${encodeURIComponent(tenantId)}`, {
    method: 'DELETE',
    session,
  });
}

export function listTenantMembers(session, tenantId) {
  return request(`/tenants/${tenantId}/members`, { session, tenantId });
}

export function inviteTenantMember(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/members`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateTenantMemberRole(session, tenantId, userId, role) {
  return request(`/tenants/${tenantId}/members/${userId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: { role },
  });
}

export function removeTenantMember(session, tenantId, userId) {
  return request(`/tenants/${tenantId}/members/${userId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}


export function upsertWhatsAppChannel(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/channels/whatsapp`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function getWhatsAppChannelHealth(session, tenantId) {
  return request(`/tenants/${tenantId}/channels/whatsapp/health`, { session, tenantId });
}

export function patchWhatsAppChannelMode(session, tenantId, accountMode, reason) {
  return request(`/tenants/${tenantId}/channels/whatsapp/mode`, {
    method: 'PATCH',
    session,
    tenantId,
    body: { account_mode: accountMode, reason },
  });
}

export function getWebChannel(session, tenantId) {
  return request(`/tenants/${tenantId}/channels/web`, { session, tenantId });
}

export function listMessengerChannels(session, tenantId) {
  return request(`/tenants/${tenantId}/channels/messenger`, { session, tenantId });
}

export function upsertMessengerChannel(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/channels/messenger`, {
    method: 'PUT',
    session,
    tenantId,
    body: payload,
  });
}

export function upsertWebChannel(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/channels/web`, {
    method: 'PUT',
    session,
    tenantId,
    body: payload,
  });
}

export function getKnowledgeStorageSettings(session, tenantId) {
  return request(`/tenants/${tenantId}/knowledge/storage`, { session, tenantId });
}

export function updateKnowledgeStorageSettings(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/knowledge/storage`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}


export function evaluateIntent(session, tenantId, payload) {
  return request('/intents/evaluate', {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function listKnowledgeDocuments(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return request(`/knowledge/documents${query ? `?${query}` : ''}`, { session, tenantId });
}

export function uploadKnowledgeDocument(session, tenantId, payload) {
  const formData = new FormData();
  formData.set('tenant_id', tenantId);
  formData.set('title', payload.title);
  formData.set('document_type', payload.document_type || 'reference');
  formData.set('visibility', payload.visibility || 'tenant');
  formData.set('file', payload.file);
  return uploadMultipart('/knowledge/documents/upload', { formData, session, tenantId });
}

export function createKnowledgeDocument(session, tenantId, payload) {
  return request('/knowledge/documents', {
    method: 'POST',
    session,
    tenantId,
    body: { ...payload, tenant_id: tenantId },
  });
}

export function updateKnowledgeDocument(session, tenantId, documentId, payload) {
  return request(`/knowledge/documents/${documentId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function indexKnowledgeDocument(session, tenantId, documentId) {
  return request(`/knowledge/documents/${documentId}/index`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function reindexAllKnowledgeDocuments(session, tenantId) {
  return request('/knowledge/reindex-all', {
    method: 'POST',
    session,
    tenantId,
  });
}

export function deleteKnowledgeDocument(session, tenantId, documentId) {
  return request(`/knowledge/documents/${documentId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}


export function startConversation(session, tenantId, payload) {
  return request('/conversations/start', {
    method: 'POST',
    session,
    tenantId,
    body: { ...payload, tenant_id: tenantId },
  });
}

export function listConversations(session, tenantId) {
  return request('/conversations', { session, tenantId });
}

export function listComplaintConversations(session, tenantId) {
  return request('/conversations/complaints', { session, tenantId });
}

export function conversationMessageMediaUrl(session, tenantId, conversationId, messageId) {
  const safeConversationId = encodeURIComponent(conversationId);
  const safeMessageId = encodeURIComponent(messageId);
  const safeTenantId = encodeURIComponent(tenantId);

  return coreApiPath(
    session,
    `/conversations/${safeConversationId}/messages/${safeMessageId}/media?tenant_id=${safeTenantId}`,
  );
}

export function getConversation(session, tenantId, conversationId) {
  return request(`/conversations/${conversationId}`, { session, tenantId });
}

export function sendConversationMessage(session, tenantId, conversationId, payload) {
  return request(`/conversations/${conversationId}/messages`, {
    method: 'POST',
    session,
    tenantId,
    body: {
      tenant_id: tenantId,
      conversation_id: conversationId,
      direction: 'outbound',
      sender_actor_type: 'agent',
      message_type: 'text',
      ...payload,
    },
  });
}

export function createConversationHandoff(session, tenantId, conversationId, reason) {
  return request(`/conversations/${conversationId}/handoff`, {
    method: 'POST',
    session,
    tenantId,
    body: { reason },
  });
}

export function acceptConversationHandoff(session, tenantId, conversationId) {
  return request(`/conversations/${conversationId}/handoff/accept`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function releaseConversation(session, tenantId, conversationId) {
  return request(`/conversations/${conversationId}/release`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function openConversationStream(session, tenantId) {
  return new WebSocket(
    coreWebSocketPath(session, '/conversations/stream', { tenant_id: tenantId }),
  );
}

export function listAppointmentFeedback(session, tenantId, appointmentId) {
  return request(`/appointments/${appointmentId}/feedback`, { session, tenantId });
}

export function createAppointmentFeedback(session, tenantId, appointmentId, payload) {
  return request(`/appointments/${appointmentId}/feedback`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function getResourceAvailability(session, tenantId, resourceId, { date, serviceId } = {}) {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (serviceId) params.set('service_id', serviceId);
  const query = params.toString();
  return request(
    `/tenants/${tenantId}/resources/${resourceId}/availability${query ? `?${query}` : ''}`,
    { session, tenantId },
  );
}

export function getTenantAvailability(session, tenantId, { date, serviceId } = {}) {
  const params = new URLSearchParams();
  if (date) params.set('date', date);
  if (serviceId) params.set('service_id', serviceId);
  const query = params.toString();
  return request(
    `/tenants/${tenantId}/availability${query ? `?${query}` : ''}`,
    { session, tenantId },
  );
}

export function listWhatsappTemplates(session, tenantId, { purpose, status } = {}) {
  const params = new URLSearchParams();
  if (purpose) params.set('purpose', purpose);
  if (status) params.set('status', status);
  const query = params.toString();
  return request(
    `/tenants/${tenantId}/whatsapp/templates${query ? `?${query}` : ''}`,
    { session, tenantId },
  );
}

export function getWhatsappTemplate(session, tenantId, templateId) {
  return request(`/tenants/${tenantId}/whatsapp/templates/${templateId}`, { session, tenantId });
}

export function createWhatsappTemplate(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/whatsapp/templates`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateWhatsappTemplate(session, tenantId, templateId, payload) {
  return request(`/tenants/${tenantId}/whatsapp/templates/${templateId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deleteWhatsappTemplate(session, tenantId, templateId) {
  return request(`/tenants/${tenantId}/whatsapp/templates/${templateId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function syncWhatsappTemplates(session, tenantId) {
  return request(`/tenants/${tenantId}/whatsapp/templates/sync`, {
    method: 'POST',
    session,
    tenantId,
    body: {},
  });
}

export function listServices(session, tenantId, { includeInactive = false } = {}) {
  const query = includeInactive ? '?include_inactive=true' : '';
  return request(`/tenants/${tenantId}/services${query}`, { session, tenantId });
}

export function createService(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/services`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateService(session, tenantId, serviceId, payload) {
  return request(`/tenants/${tenantId}/services/${serviceId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deactivateService(session, tenantId, serviceId) {
  return request(`/tenants/${tenantId}/services/${serviceId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function reorderServices(session, tenantId, order) {
  return request(`/tenants/${tenantId}/services/reorder`, {
    method: 'POST',
    session,
    tenantId,
    body: { order },
  });
}

export function listQualificationQuestions(session, tenantId) {
  return request(`/tenants/${tenantId}/qualification-questions`, {
    session,
    tenantId,
  });
}

export function createQualificationQuestion(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/qualification-questions`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateQualificationQuestion(session, tenantId, questionId, payload) {
  return request(`/tenants/${tenantId}/qualification-questions/${questionId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deleteQualificationQuestion(session, tenantId, questionId) {
  return request(`/tenants/${tenantId}/qualification-questions/${questionId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function reorderQualificationQuestions(session, tenantId, order) {
  return request(`/tenants/${tenantId}/qualification-questions/reorder`, {
    method: 'POST',
    session,
    tenantId,
    body: { order },
  });
}

export function listMediaAssets(session, tenantId, { kind, tag } = {}) {
  const params = new URLSearchParams();
  if (kind) params.set('kind', kind);
  if (tag) params.set('tag', tag);
  const qs = params.toString();
  return request(
    `/tenants/${tenantId}/media${qs ? `?${qs}` : ''}`,
    { session, tenantId },
  );
}

export async function uploadMediaAsset(session, tenantId, { kind, label, description, tags, file }) {
  const formData = new FormData();
  formData.append('kind', kind);
  formData.append('label', label);
  if (description) formData.append('description', description);
  if (tags && tags.length) formData.append('tags', tags.join(','));
  formData.append('file', file);
  const response = await fetch(coreApiPath(session, `/tenants/${tenantId}/media`), {
    method: 'POST',
    credentials: 'include',
    headers: {
      accept: 'application/json',
      ...(session?.accessToken ? { authorization: `Bearer ${session.accessToken}` } : {}),
      ...(tenantId ? { 'X-Tenant-Id': tenantId } : {}),
    },
    body: formData,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload?.detail || detail;
    } catch { /* noop */ }
    throw new Error(detail);
  }
  return response.json();
}

export function updateMediaAsset(session, tenantId, assetId, payload) {
  return request(`/tenants/${tenantId}/media/${assetId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deleteMediaAsset(session, tenantId, assetId) {
  return request(`/tenants/${tenantId}/media/${assetId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listPromotions(session, tenantId, { includeInactive = true } = {}) {
  const query = includeInactive ? '' : '?include_inactive=false';
  return request(`/tenants/${tenantId}/promotions${query}`, { session, tenantId });
}

export function createPromotion(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/promotions`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updatePromotion(session, tenantId, promotionId, payload) {
  return request(`/tenants/${tenantId}/promotions/${promotionId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deletePromotion(session, tenantId, promotionId) {
  return request(`/tenants/${tenantId}/promotions/${promotionId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listBranches(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/branches${query ? `?${query}` : ''}`, { session, tenantId });
}

export function createBranch(session, tenantId, payload) {
  return request('/branches', {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateBranch(session, tenantId, branchId, payload) {
  return request(`/branches/${branchId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deactivateBranch(session, tenantId, branchId) {
  return request(`/branches/${branchId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listTreatmentPackages(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/packages${query ? `?${query}` : ''}`, { session, tenantId });
}

export function createTreatmentPackage(session, tenantId, payload) {
  return request('/packages', {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateTreatmentPackage(session, tenantId, packageId, payload) {
  return request(`/packages/${packageId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deactivateTreatmentPackage(session, tenantId, packageId) {
  return request(`/packages/${packageId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listContactPackages(session, tenantId, contactId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/contacts/${contactId}/packages${query ? `?${query}` : ''}`, {
    session,
    tenantId,
  });
}

export function assignContactPackage(session, tenantId, contactId, payload) {
  return request(`/contacts/${contactId}/packages`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateContactPackage(session, tenantId, contactId, contactPackageId, payload) {
  return request(`/contacts/${contactId}/packages/${contactPackageId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function refundContactPackage(session, tenantId, contactId, contactPackageId) {
  return request(`/contacts/${contactId}/packages/${contactPackageId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listSubscriptionPlans(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/subscription-plans${query ? `?${query}` : ''}`, { session, tenantId });
}

export function createSubscriptionPlan(session, tenantId, payload) {
  return request('/subscription-plans', {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateSubscriptionPlan(session, tenantId, planId, payload) {
  return request(`/subscription-plans/${planId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function archiveSubscriptionPlan(session, tenantId, planId) {
  return request(`/subscription-plans/${planId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listContactSubscriptions(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/subscriptions${query ? `?${query}` : ''}`, { session, tenantId });
}

export function cancelContactSubscription(session, tenantId, subscriptionId) {
  return request(`/subscriptions/${subscriptionId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listResources(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/resources${query ? `?${query}` : ''}`, { session, tenantId });
}

export function createResource(session, tenantId, payload) {
  return request('/resources', {
    method: 'POST',
    session,
    tenantId,
    body: { ...payload, tenant_id: tenantId },
  });
}

export function updateResource(session, tenantId, resourceId, payload) {
  return request(`/resources/${resourceId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function listAppointments(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/appointments${query ? `?${query}` : ''}`, { session, tenantId });
}

export function createAppointment(session, tenantId, payload) {
  return request('/appointments', {
    method: 'POST',
    session,
    tenantId,
    body: { ...payload, tenant_id: tenantId },
  });
}

export function updateAppointment(session, tenantId, appointmentId, payload) {
  return request(`/appointments/${appointmentId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function cancelAppointment(session, tenantId, appointmentId) {
  return request(`/appointments/${appointmentId}/cancel`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function listServiceRequests(session, tenantId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const query = params.toString();
  return request(`/service-requests${query ? `?${query}` : ''}`, { session, tenantId });
}

export function createServiceRequest(session, tenantId, payload) {
  return request('/service-requests', {
    method: 'POST',
    session,
    tenantId,
    body: { ...payload, tenant_id: tenantId },
  });
}

export function patchServiceRequest(session, tenantId, requestId, payload) {
  return request(`/service-requests/${requestId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function getQuoteForSr(session, tenantId, requestId) {
  return request(`/service-requests/${requestId}/quote`, { session, tenantId });
}

export function createQuote(session, tenantId, requestId, payload) {
  return request(`/service-requests/${requestId}/quotes`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function patchQuote(session, tenantId, quoteId, payload) {
  return request(`/quotes/${quoteId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function sendQuote(session, tenantId, quoteId) {
  return request(`/quotes/${quoteId}/send`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function listContactTags(session, tenantId) {
  return request(`/tenants/${tenantId}/contact-tags`, { session, tenantId });
}

export function createContactTag(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/contact-tags`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateContactTag(session, tenantId, tagId, payload) {
  return request(`/tenants/${tenantId}/contact-tags/${tagId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deleteContactTag(session, tenantId, tagId) {
  return request(`/tenants/${tenantId}/contact-tags/${tagId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listContacts(session, tenantId, { q, tagId, limit, offset } = {}) {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (tagId) params.set('tag_id', tagId);
  if (limit != null) params.set('limit', String(limit));
  if (offset != null) params.set('offset', String(offset));
  const qs = params.toString();
  return request(`/contacts${qs ? `?${qs}` : ''}`, { session, tenantId });
}

export function getContactProfile(session, tenantId, contactId) {
  return request(`/contacts/${contactId}/profile`, { session, tenantId });
}

// TASK-0082 / BUG22: dedicated endpoint to mutate a contact's phone_e164.
// Requires role manager+ on the tenant and produces an audit row.
export function updateContactPhone(session, tenantId, contactId, { phone_e164, reason }) {
  return request(`/contacts/${contactId}/phone`, {
    method: 'PATCH',
    session,
    tenantId,
    body: { phone_e164, reason: reason || null },
  });
}

export function assignContactTags(session, tenantId, contactId, tagIds) {
  return request(`/contacts/${contactId}/tags`, {
    method: 'POST',
    session,
    tenantId,
    body: { tag_ids: tagIds },
  });
}

export function unassignContactTag(session, tenantId, contactId, tagId) {
  return request(`/contacts/${contactId}/tags/${tagId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function listContactNotes(session, tenantId, contactId) {
  return request(`/contacts/${contactId}/notes`, { session, tenantId });
}

export function listContactConsent(session, tenantId, contactId, { limit, offset } = {}) {
  const params = new URLSearchParams();
  if (limit != null) params.set('limit', String(limit));
  if (offset != null) params.set('offset', String(offset));
  const query = params.toString();
  return request(`/contacts/${contactId}/consent${query ? `?${query}` : ''}`, {
    session,
    tenantId,
  });
}

export function createContactNote(session, tenantId, contactId, body) {
  return request(`/contacts/${contactId}/notes`, {
    method: 'POST',
    session,
    tenantId,
    body: { body },
  });
}

export function listCampaigns(session, tenantId, { status } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  const query = params.toString();
  return request(`/tenants/${tenantId}/campaigns${query ? `?${query}` : ''}`, {
    session,
    tenantId,
  });
}

export function getCampaign(session, tenantId, campaignId) {
  return request(`/tenants/${tenantId}/campaigns/${campaignId}`, { session, tenantId });
}

export function createCampaign(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/campaigns`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateCampaign(session, tenantId, campaignId, payload) {
  return request(`/tenants/${tenantId}/campaigns/${campaignId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function previewCampaign(session, tenantId, campaignId) {
  return request(`/tenants/${tenantId}/campaigns/${campaignId}/preview`, {
    method: 'POST',
    session,
    tenantId,
    body: {},
  });
}

export function launchCampaign(session, tenantId, campaignId, payload = {}) {
  return request(`/tenants/${tenantId}/campaigns/${campaignId}/launch`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function cancelCampaign(session, tenantId, campaignId) {
  return request(`/tenants/${tenantId}/campaigns/${campaignId}/cancel`, {
    method: 'POST',
    session,
    tenantId,
    body: {},
  });
}

export function listContactSegments(session, tenantId, { kind } = {}) {
  const params = new URLSearchParams();
  if (kind) params.set('kind', kind);
  const query = params.toString();
  return request(`/tenants/${tenantId}/segments${query ? `?${query}` : ''}`, {
    session,
    tenantId,
  });
}

export function createContactSegment(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/segments`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function updateContactSegment(session, tenantId, segmentId, payload) {
  return request(`/tenants/${tenantId}/segments/${segmentId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function deleteContactSegment(session, tenantId, segmentId) {
  return request(`/tenants/${tenantId}/segments/${segmentId}`, {
    method: 'DELETE',
    session,
    tenantId,
  });
}

export function previewContactSegment(session, tenantId, segmentId, { limit } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  const query = params.toString();
  return request(
    `/tenants/${tenantId}/segments/${segmentId}/preview${query ? `?${query}` : ''}`,
    { session, tenantId },
  );
}

export function refreshContactSegment(session, tenantId, segmentId) {
  return request(`/tenants/${tenantId}/segments/${segmentId}/refresh`, {
    method: 'POST',
    session,
    tenantId,
    body: {},
  });
}

function buildAnalyticsQuery({ fromDate, toDate } = {}) {
  const params = new URLSearchParams();
  if (fromDate) params.set('from_date', fromDate);
  if (toDate) params.set('to_date', toDate);
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function getAnalyticsOverview(session, tenantId, range = {}) {
  return request(`/analytics/overview${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsConversations(session, tenantId, range = {}) {
  return request(`/analytics/conversations${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsAppointments(session, tenantId, range = {}) {
  return request(`/analytics/appointments${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsContacts(session, tenantId, range = {}) {
  return request(`/analytics/contacts${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsFunnel(session, tenantId, range = {}) {
  return request(`/analytics/funnel${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsCampaigns(session, tenantId, range = {}) {
  return request(`/analytics/campaigns${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsReferrals(session, tenantId, range = {}) {
  return request(`/analytics/referrals${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getAnalyticsAgents(session, tenantId, range = {}) {
  return request(`/analytics/agents${buildAnalyticsQuery(range)}`, { session, tenantId });
}

export function getTenantPaymentSettings(session, tenantId) {
  return request(`/tenants/${tenantId}/payments/settings`, { session, tenantId });
}

export function updateTenantPaymentSettings(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/payments/settings`, {
    method: 'PUT',
    session,
    tenantId,
    body: payload,
  });
}

export function generateAppointmentPaymentLink(session, tenantId, appointmentId, payload = {}) {
  return request(`/appointments/${appointmentId}/payment-link`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function sendAppointmentPaymentLink(session, tenantId, appointmentId) {
  return request(`/appointments/${appointmentId}/send-payment`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function updateAppointmentPaymentStatus(session, tenantId, appointmentId, payload) {
  return request(`/appointments/${appointmentId}/payment-status`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

// TASK-0065: Outbound DLQ (mensajes que el event_worker no logró entregar).
export function listOutboundDlq(session, tenantId, { since, until, limit, errorCode } = {}) {
  const params = new URLSearchParams();
  if (since) params.set('since', since);
  if (until) params.set('until', until);
  if (limit) params.set('limit', String(limit));
  if (errorCode) params.set('error_code', errorCode);
  const qs = params.toString();
  return request(`/tenants/${tenantId}/outbound/dlq${qs ? `?${qs}` : ''}`, {
    session,
    tenantId,
  });
}

export function retryOutboundDlqMessage(session, tenantId, messageId) {
  return request(`/tenants/${tenantId}/outbound/dlq/${messageId}/retry`, {
    method: 'POST',
    session,
    tenantId,
  });
}

// TASK-0076: páginas legales por tenant (Términos / Privacidad / Consent).
export function listLegalDocuments(session, tenantId, { kind } = {}) {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return request(`/tenants/${tenantId}/legal${qs}`, { session, tenantId });
}

export function createLegalDocumentDraft(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/legal`, {
    method: 'POST',
    session,
    tenantId,
    body: payload,
  });
}

export function publishLegalDocument(session, tenantId, documentId) {
  return request(`/tenants/${tenantId}/legal/${documentId}/publish`, {
    method: 'POST',
    session,
    tenantId,
  });
}

export function legalDocumentPublicUrl(session, tenantId, kind) {
  // Built from the configured core base URL so the admin can copy/share
  // the same link the bot inserts in the consent template.
  return `${coreApiPath(session, `/tenants/${tenantId}/legal/${kind}`)}`;
}

// ─── Módulo Influencer / Ravit Studio (UI-INFLU-002) ──────────────────────

/**
 * Chequea si el tenant tiene el módulo influencer activo.
 *
 * El backend (TASK-INFLU-001) monta `GET /v1/influencer/_health` con el gate
 * `ensure_module_enabled`: devuelve 200 con `{module:'influencer',
 * status:'active'}` si el tenant tiene la fila en `app.tenant_modules` con
 * `enabled=true`, o 404 si no — decisión D2 explícita (NO filtra existencia
 * del feature; el tenant que pide cualquier endpoint del módulo sin tenerlo
 * activado recibe 404 indistinguible de una ruta inexistente).
 *
 * El frontend traduce el 404 a `false` y lo usa en `InfluencerShell` para
 * mostrar el banner "Módulo no habilitado" en lugar de un error genérico.
 * Cualquier otro error (401/403/5xx) se propaga al ErrorBoundary.
 *
 * @param {object} session - Sesión activa (usa Bearer JWT).
 * @param {string} tenantId - UUID del tenant activo.
 * @returns {Promise<boolean>} `true` si el módulo está activo para el tenant,
 *   `false` si el backend respondió 404 (módulo no habilitado).
 */
export async function isInfluencerEnabled(session, tenantId) {
  try {
    await request('/influencer/_health', { session, tenantId });
    return true;
  } catch (err) {
    if (err?.status === 404) {
      return false;
    }
    throw err;
  }
}
