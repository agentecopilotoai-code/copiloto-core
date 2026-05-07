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
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export function createTenant(session, payload) {
  return request('/tenant-signup', { method: 'POST', session, body: payload });
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
