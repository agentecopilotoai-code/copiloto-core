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

async function request(path, { body, method = 'GET', session, tenantId } = {}) {
  const response = await fetch(adminPath(path), {
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
  return request('/v1/tenants', { method: 'POST', session, body: payload });
}

export function updateTenantSettings(session, tenantId, payload) {
  return request(`/v1/tenants/${tenantId}/settings`, {
    method: 'PATCH',
    session,
    tenantId,
    body: payload,
  });
}

export function listAuditLogs(session, tenantId) {
  return request('/v1/audit-logs', { session, tenantId });
}
