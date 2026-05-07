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
