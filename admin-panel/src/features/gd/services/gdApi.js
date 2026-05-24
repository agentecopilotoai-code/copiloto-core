/**
 * Cliente API del módulo Gestión Documental.
 *
 * Llama a `/api/v1/gd/*`, `/api/v1/core/*` y `/gd/verificar/*` del backend.
 * Reusa el mismo patrón de `coreApi.js` (session.api.baseUrl + JWT) pero la
 * URL base es distinta porque GD no vive bajo `/admin/api/core/v1`.
 *
 * Convenciones:
 *  - Todos los fetch incluyen `X-Tenant-Id` (resuelto por `session.tenant`).
 *  - `Authorization: Bearer <jwt>` viene del wrapper `authHeaders()`.
 *  - 403 con `code='gd_profile_missing_or_inactive'` → throw `GdNoProfileError`
 *    para que la UI muestre "Solicite activación al administrador".
 */

const DEFAULT_BASE = '/api/v1';

export class GdNoProfileError extends Error {
  constructor(message = 'gd_profile_missing_or_inactive') {
    super(message);
    this.name = 'GdNoProfileError';
    this.code = 'gd_profile_missing_or_inactive';
  }
}

export class GdHttpError extends Error {
  constructor(status, body) {
    super(`gd_http_${status}`);
    this.status = status;
    this.body = body;
    this.name = 'GdHttpError';
  }
}

function authHeaders(session) {
  const headers = { 'Content-Type': 'application/json' };
  const token = session?.token || session?.jwt;
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const tenantId = session?.tenant?.id || session?.tenantId;
  if (tenantId) headers['X-Tenant-Id'] = tenantId;
  return headers;
}

function gdPath(session, path) {
  const base = session?.api?.gdBaseUrl || DEFAULT_BASE;
  return `${base}${path}`;
}

async function gdFetch(session, path, { method = 'GET', body, params } = {}) {
  const url = new URL(gdPath(session, path), window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v));
      }
    });
  }
  const res = await fetch(url.toString().replace(window.location.origin, ''), {
    method,
    headers: authHeaders(session),
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) {
    if (
      res.status === 403 &&
      parsed?.detail?.code === 'gd_profile_missing_or_inactive'
    ) {
      throw new GdNoProfileError();
    }
    throw new GdHttpError(res.status, parsed);
  }
  return parsed;
}

function safeJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

// ─── Endpoints específicos ───────────────────────────────────────────────

/** GET /api/v1/gd/me — perfil GD del usuario. */
export const getMyGdProfile = (session) => gdFetch(session, '/gd/me');

/** GET /api/v1/gd/entidad — datos institucionales para constancias. */
export const getEntidadPublica = (session) => gdFetch(session, '/gd/entidad');

/** GET /api/v1/core/auditoria?entidad_tipo=&entidad_id=&limit= */
export function listAuditoria(session, { entidadTipo, entidadId, limit = 50 } = {}) {
  return gdFetch(session, '/core/auditoria', {
    params: {
      entidad_tipo: entidadTipo,
      entidad_id: entidadId,
      limit,
    },
  });
}

/** GET /api/v1/gd/ventanilla/radicados con scope. */
export function listRadicados(session, { scope, q, estado, canal_id, limit = 50 } = {}) {
  return gdFetch(session, '/gd/ventanilla/radicados', {
    params: { scope, q, estado, canal_id, limit },
  });
}

/** GET /api/v1/gd/tareas/buzon — buzón del usuario. */
export function listMyBuzon(session, { scope, limit = 50 } = {}) {
  return gdFetch(session, '/gd/me/buzon', { params: { scope, limit } });
}

/** POST /api/v1/gd/ventanilla/radicados — crear radicado de entrada. */
export function crearRadicadoEntrada(session, payload) {
  return gdFetch(session, '/gd/ventanilla/radicados', {
    method: 'POST',
    body: payload,
  });
}

/** GET /api/v1/gd/pqrsd — listar PQRSD. */
export function listPQRSD(session, { scope, estado, vencimiento, limit = 50 } = {}) {
  return gdFetch(session, '/gd/pqrsd', {
    params: { scope, estado, vencimiento, limit },
  });
}

/** GET único entidad — abstracción genérica usada por las fichas. */
export function fetchEntidad(session, ruta) {
  return gdFetch(session, ruta);
}

// Internal exports for testing.
export const _internal = { gdPath, gdFetch, authHeaders };
