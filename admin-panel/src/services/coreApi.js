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

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export function createTenant(session, payload) {
  return request('/tenant-signup', { method: 'POST', session, body: payload });
}

export function getTenant(session, tenantId) {
  return request(`/tenants/${tenantId}`, { session, tenantId });
}

export function updateTenant(session, tenantId, payload) {
  return request(`/tenants/${tenantId}`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
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
