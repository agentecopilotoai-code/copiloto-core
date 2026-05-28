/**
 * Cliente HTTP del Core API.
 *
 * Solo expone funciones para endpoints transversales del core. Los
 * módulos de producto traen su propio cliente (ej. `gdApi.js` en el
 * módulo de Gestión Documental) y NO se mezclan con éste.
 */
import { adminPath } from './adminSession.js';

function buildHeaders(session, tenantId, body) {
  const headers = { accept: 'application/json' };
  if (body !== undefined) headers['content-type'] = 'application/json';
  if (session?.accessToken) headers.authorization = `Bearer ${session.accessToken}`;
  if (tenantId) headers['X-Tenant-Id'] = tenantId;
  return headers;
}

function coreApiPath(session, path) {
  const baseUrl = session?.api?.baseUrl || '/admin/api/core/v1';
  return adminPath(`${baseUrl}${path}`);
}

function _formatPydanticError(detail) {
  if (!Array.isArray(detail)) return null;
  const parts = detail.map((item) => {
    const loc = Array.isArray(item?.loc)
      ? item.loc.filter((p, i) => !(i === 0 && p === 'body')).join('.')
      : 'campo';
    return `${loc}: ${item?.msg || 'inválido'}`;
  });
  return parts.join(' · ');
}

/**
 * Helper HTTP genérico. Hace JSON request al Core API via el BFF
 * (`/admin/api/core/v1/*`). Devuelve la respuesta parseada como JSON,
 * o `null` para 204. En error tira una `Error` con `.status` y `.detail`.
 */
export async function request(path, { method = 'GET', session, tenantId, body } = {}) {
  const response = await fetch(coreApiPath(session, path), {
    credentials: 'include',
    method,
    headers: buildHeaders(session, tenantId, body),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    let rawDetail = null;
    try {
      const payload = await response.json();
      rawDetail = payload?.detail ?? payload ?? null;
      if (typeof payload?.detail === 'string') {
        detail = payload.detail;
      } else if (Array.isArray(payload?.detail)) {
        detail = _formatPydanticError(payload.detail) || JSON.stringify(payload.detail);
      } else if (payload?.detail && typeof payload.detail === 'object') {
        detail = payload.detail.message || JSON.stringify(payload.detail);
      } else if (payload) {
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
  if (response.status === 204) return null;
  return response.json();
}

// ─── /v1/me/* — Mi cuenta ───────────────────────────────────────────────────

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
export function patchMyNotifications(session, notification_matrix) {
  return request('/me/notifications', {
    method: 'PATCH', session, body: { notification_matrix },
  });
}
export function listMySessions(session) {
  return request('/me/sessions', { session });
}
export function revokeMySession(session, sessionId) {
  return request(`/me/sessions/${sessionId}`, { method: 'DELETE', session });
}
export function listMyTenants(session) {
  return request('/me/tenants', { session });
}

// ─── /v1/tenant-signup — self-service ──────────────────────────────────────

export function createTenant(session, payload) {
  return request('/tenant-signup', { method: 'POST', session, body: payload });
}

// ─── /v1/tenants/* — Platform admin cross-tenant ───────────────────────────

/**
 * Platform-owner crea un tenant para un tercero desde Fleet.
 * NO auto-asigna al caller como owner. El caller queda en Fleet.
 */
export function createTenantAsPlatformOwner(session, payload) {
  return request('/tenants', { method: 'POST', session, body: payload });
}

export function listFleetTenants(session, { status, country, vertical, search, limit, offset } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (country) params.set('country_code', country);
  if (vertical) params.set('vertical_code', vertical);
  if (search) params.set('search', search);
  if (limit !== undefined && limit !== null) params.set('limit', String(limit));
  if (offset !== undefined && offset !== null) params.set('offset', String(offset));
  const qs = params.toString();
  return request(`/tenants${qs ? `?${qs}` : ''}`, { session });
}

export function getTenant(session, tenantId) {
  return request(`/tenants/${tenantId}`, { session });
}

export function updateTenant(session, tenantId, payload) {
  return request(`/tenants/${tenantId}`, { method: 'PATCH', session, body: payload });
}

export function patchTenantStatus(session, tenantId, status) {
  return request(`/tenants/${tenantId}/status`, {
    method: 'PATCH', session, body: { status },
  });
}

// Miembros del tenant (gestión cross-tenant desde admin).
export function listTenantMembers(session, tenantId) {
  return request(`/tenants/${tenantId}/members`, { session });
}
export function inviteTenantMember(session, tenantId, payload) {
  return request(`/tenants/${tenantId}/members`, {
    method: 'POST', session, body: payload,
  });
}
export function updateTenantMemberRole(session, tenantId, userId, role) {
  return request(`/tenants/${tenantId}/members/${userId}`, {
    method: 'PATCH', session, body: { role },
  });
}
export function removeTenantMember(session, tenantId, userId) {
  return request(`/tenants/${tenantId}/members/${userId}`, {
    method: 'DELETE', session,
  });
}

// ─── /v1/platform/* — Platform admin observability + config ────────────────

export function getSystemHealth(session) {
  return request('/platform/metrics/health', { session });
}
export function getPlatformBillingMrr(session) {
  return request('/platform/billing/mrr', { session });
}
export function getPlatformIncidents(session, { status, limit } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (limit) params.set('limit', String(limit));
  const qs = params.toString();
  return request(`/platform/incidents${qs ? `?${qs}` : ''}`, { session });
}
export function getPlatformOutboundDlq(session) {
  return request('/platform/outbound-dlq', { session });
}
export function retryPlatformOutboundDlq(session, payload) {
  return request('/platform/outbound-dlq/retry', {
    method: 'POST', session, body: payload,
  });
}
export function getPlatformRunbooks(session) {
  return request('/platform/runbooks', { session });
}
export function getPlatformRunbook(session, slug) {
  return request(`/platform/runbooks/${encodeURIComponent(slug)}`, { session });
}

// Feature flags CRUD (Fase 2 write).
export function getPlatformFeatureFlags(session) {
  return request('/platform/feature-flags', { session });
}
export function createPlatformFeatureFlag(session, payload) {
  return request('/platform/feature-flags', { method: 'POST', session, body: payload });
}
export function patchPlatformFeatureFlag(session, key, payload) {
  return request(`/platform/feature-flags/${key}`, {
    method: 'PATCH', session, body: payload,
  });
}
export function deletePlatformFeatureFlag(session, key) {
  return request(`/platform/feature-flags/${key}`, { method: 'DELETE', session });
}

// AI providers (cross-modalidad).
export function listAIProviders(session) {
  return request('/platform/ai-providers', { session });
}
export function updateAIProvider(session, modality, payload) {
  return request(`/platform/ai-providers/${modality}`, {
    method: 'PATCH', session, body: payload,
  });
}
export function testAIProvider(session, modality, body) {
  return request(`/platform/ai-providers/${modality}/test`, {
    method: 'POST', session, body,
  });
}

// Email providers (v2.0.0 — multi-provider con fallback chain).
export function listEmailProviders(session) {
  return request('/platform/email-providers', { session });
}
export function createEmailProvider(session, payload) {
  return request('/platform/email-providers', {
    method: 'POST', session, body: payload,
  });
}
export function patchEmailProvider(session, providerId, payload) {
  return request(`/platform/email-providers/${providerId}`, {
    method: 'PATCH', session, body: payload,
  });
}
export function deleteEmailProvider(session, providerId) {
  return request(`/platform/email-providers/${providerId}`, {
    method: 'DELETE', session,
  });
}
export function testEmailProvider(session, providerId, payload) {
  return request(`/platform/email-providers/${providerId}/test`, {
    method: 'POST', session, body: payload,
  });
}

// Tenant modules (activación opt-in por tenant).
export function listTenantModules(session, { module, enabled, tenantSearch } = {}) {
  const params = new URLSearchParams();
  if (module) params.set('module', module);
  if (enabled !== undefined && enabled !== null) params.set('enabled', String(enabled));
  if (tenantSearch) params.set('tenant_search', tenantSearch);
  const qs = params.toString();
  return request(`/platform/tenant-modules${qs ? `?${qs}` : ''}`, { session });
}
export function updateTenantModule(session, tenantId, moduleCode, { enabled, plan, notes } = {}) {
  const body = {};
  if (enabled !== undefined) body.enabled = enabled;
  if (plan !== undefined) body.plan = plan;
  if (notes !== undefined) body.notes = notes;
  return request(`/platform/tenant-modules/${tenantId}/${moduleCode}`, {
    method: 'PATCH', session, body,
  });
}

// Roles & capabilities CRUD (Fase 2).
export function listPlatformRoles(session) {
  return request('/platform/roles', { session });
}
export function createPlatformRole(session, payload) {
  return request('/platform/roles', { method: 'POST', session, body: payload });
}
export function patchPlatformRole(session, code, payload) {
  return request(`/platform/roles/${code}`, { method: 'PATCH', session, body: payload });
}
export function deletePlatformRole(session, code) {
  return request(`/platform/roles/${code}`, { method: 'DELETE', session });
}
export function listPlatformCapabilities(session) {
  return request('/platform/capabilities', { session });
}
export function createPlatformCapability(session, payload) {
  return request('/platform/capabilities', { method: 'POST', session, body: payload });
}
export function listRoleCapabilities(session, roleCode) {
  return request(`/platform/roles/${roleCode}/capabilities`, { session });
}
export function assignCapabilityToRole(session, roleCode, capabilityCode, accessLevel) {
  return request(`/platform/roles/${roleCode}/capabilities/${capabilityCode}`, {
    method: 'PUT', session, body: { access_level: accessLevel },
  });
}
export function revokeCapabilityFromRole(session, roleCode, capabilityCode) {
  return request(`/platform/roles/${roleCode}/capabilities/${capabilityCode}`, {
    method: 'DELETE', session,
  });
}

// ─── Support mode (platform_owner opt-in temporal por tenant) ─────────────

/**
 * Activa support_mode para un tenant. `body.justification` debe tener al menos
 * 8 caracteres — el backend (`POST /v1/me/support-mode/{tenant_id}`) lo
 * persiste en `audit_logs.metadata.justification` para la forensia del
 * cruce cross-tenant (M40 — antes el wrapper ignoraba el body y el log
 * quedaba con `justification_provided=false`).
 */
export function activateSupportMode(session, tenantId, body = {}) {
  return request(`/me/support-mode/${tenantId}`, {
    method: 'POST',
    session,
    body,
  });
}
export function deactivateSupportMode(session, tenantId) {
  return request(`/me/support-mode/${tenantId}`, { method: 'DELETE', session });
}
