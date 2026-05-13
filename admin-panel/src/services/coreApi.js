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


export function getTenantReadiness(session, tenantId, options = {}) {
  const params = new URLSearchParams();
  if (options.smokeQuestion) params.set('smoke_question', options.smokeQuestion);
  if (options.retrievalMinScore !== undefined && options.retrievalMinScore !== '') {
    params.set('retrieval_min_score', options.retrievalMinScore);
  }
  const query = params.toString();
  return request(`/tenants/${tenantId}/readiness${query ? `?${query}` : ''}`, { session, tenantId });
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
