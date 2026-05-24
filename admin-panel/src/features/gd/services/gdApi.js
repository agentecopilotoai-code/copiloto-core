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

/** POST /api/v1/gd/ventanilla/radicados/entrada — radicado de entrada (GD-API-0024). */
export function crearRadicadoEntrada(session, payload) {
  return gdFetch(session, '/gd/ventanilla/radicados/entrada', {
    method: 'POST',
    body: payload,
  });
}

/** POST /api/v1/gd/ventanilla/radicados/salida (GD-API-0025). */
export function crearRadicadoSalida(session, payload) {
  return gdFetch(session, '/gd/ventanilla/radicados/salida', {
    method: 'POST',
    body: payload,
  });
}

/** POST /api/v1/gd/ventanilla/radicados/{id}/clasificar (GD-API-0026). */
export function clasificarRadicado(session, radicadoId, payload) {
  return gdFetch(
    session,
    `/gd/ventanilla/radicados/${radicadoId}/clasificar`,
    { method: 'POST', body: payload },
  );
}

/** GET /api/v1/gd/ventanilla/cola/pendientes-clasificacion (GD-API-0031). */
export function listColaPendientesClasificacion(session, { limit = 50, canal_id, desde } = {}) {
  return gdFetch(session, '/gd/ventanilla/cola/pendientes-clasificacion', {
    params: { limit, canal_id, desde },
  });
}

/**
 * GET /api/v1/gd/ventanilla/constancias/{codigo} (PÚBLICO sin auth — GD-API-0030).
 * Permite verificar autenticidad de un radicado escaneando el QR. Devuelve
 * datos NO sensibles (numero_radicado, fecha, estado, asunto_resumido).
 */
export function verificarConstanciaPublica(codigo, baseUrl = '/api/v1') {
  return fetch(`${baseUrl}/gd/ventanilla/constancias/${encodeURIComponent(codigo)}`, {
    headers: { 'Content-Type': 'application/json' },
  }).then(async (res) => {
    const text = await res.text();
    const body = text ? safeJson(text) : null;
    if (!res.ok) throw new GdHttpError(res.status, body);
    return body;
  });
}

/** GET /api/v1/gd/catalogos/canales — catálogo de canales activos. */
export function listCanales(session) {
  return gdFetch(session, '/gd/catalogos/canales');
}

/** GET /api/v1/gd/terceros?q=... — búsqueda de terceros (GD-API-0033). */
export function buscarTerceros(session, q, { limit = 10 } = {}) {
  return gdFetch(session, '/gd/terceros', { params: { q, limit } });
}

/** POST /api/v1/gd/terceros — crear tercero inline (con dedupe del backend). */
export function crearTercero(session, payload) {
  return gdFetch(session, '/gd/terceros', { method: 'POST', body: payload });
}

/** GET /api/v1/gd/estructura/dependencias — para selector destino. */
export function listDependencias(session) {
  return gdFetch(session, '/gd/estructura/dependencias');
}

/**
 * POST /api/v1/gd/ia/extraer — sugerencia IA opcional (GD-API-0079).
 * Devuelve `{ resumen, tipo_clasificacion_sugerido, dependencia_sugerida }`.
 * Si IA está deshabilitada o el backend no responde, swallow → null.
 */
export function sugerenciaIaExtraer(session, payload) {
  return gdFetch(session, '/gd/ia/extraer', {
    method: 'POST', body: payload,
  });
}

// ─── UI-3: ficha + anulación + reclasif + búsqueda + reportes ────────────

/** GET ficha completa del radicado. */
export function getRadicado(session, id) {
  return gdFetch(session, `/gd/ventanilla/radicados/${id}`);
}

/** POST /gd/ventanilla/radicados/{id}/reclasificar (GD-API-0027). */
export function reclasificarRadicado(session, id, payload) {
  return gdFetch(session, `/gd/ventanilla/radicados/${id}/reclasificar`, {
    method: 'POST', body: payload,
  });
}

/** PATCH /gd/ventanilla/radicados/{id}/datos-menores (GD-API-0032). */
export function corregirDatosMenores(session, id, payload) {
  return gdFetch(session, `/gd/ventanilla/radicados/${id}/datos-menores`, {
    method: 'PATCH', body: payload,
  });
}

/** POST /gd/ventanilla/radicados/{id}/solicitar-anulacion (GD-API-0028). */
export function solicitarAnulacionRadicado(session, id, motivo) {
  return gdFetch(session, `/gd/ventanilla/radicados/${id}/solicitar-anulacion`, {
    method: 'POST', body: { motivo },
  });
}

/** GET /gd/ventanilla/anulaciones?estado=pendiente — solicitudes pendientes. */
export function listAnulacionesPendientes(session, { estado = 'pendiente', limit = 50 } = {}) {
  return gdFetch(session, '/gd/ventanilla/anulaciones', {
    params: { estado, limit },
  });
}

/** POST /gd/ventanilla/anulaciones/{id}/aprobar (GD-API-0028). */
export function aprobarAnulacion(session, solicitudId, observacion) {
  return gdFetch(session, `/gd/ventanilla/anulaciones/${solicitudId}/aprobar`, {
    method: 'POST', body: { observacion },
  });
}

/** POST /gd/ventanilla/anulaciones/{id}/rechazar (GD-API-0028). */
export function rechazarAnulacion(session, solicitudId, observacion) {
  return gdFetch(session, `/gd/ventanilla/anulaciones/${solicitudId}/rechazar`, {
    method: 'POST', body: { observacion },
  });
}

/** GET /gd/ventanilla/radicados con filtros completos (GD-API-0029). */
export function buscarRadicados(session, filtros = {}) {
  return gdFetch(session, '/gd/ventanilla/radicados', { params: filtros });
}

/** GET /gd/ventanilla/reportes — KPIs agregados de VU. */
export function getReportesVentanilla(session, { desde, hasta, scope } = {}) {
  return gdFetch(session, '/gd/ventanilla/reportes', {
    params: { desde, hasta, scope },
  });
}

/** POST /gd/ventanilla/reportes/exportar — encola exportación (PERM-REP-004). */
export function exportarReporteVentanilla(session, { formato = 'csv', desde, hasta } = {}) {
  return gdFetch(session, '/gd/ventanilla/reportes/exportar', {
    method: 'POST', body: { formato, desde, hasta },
  });
}

// ─── UI-4: Buzón de trabajo (GD-API-0038/0039) ────────────────────────────

/**
 * GET /api/v1/gd/me/buzon?carpeta=...&scope=...&limit=...
 *
 * Devuelve `{items: [{id, tipo, titulo, sub_titulo, fecha, ...}],
 *           contadores: {pqrsd, correspondencia, ...}, total}`.
 * Las carpetas son IDs simbólicas: pqrsd | correspondencia_in |
 * correspondencia_out | tareas | borradores | docs_revisar | docs_aprobar |
 * docs_firmar | notificaciones | alertas.
 */
export function getMiBuzon(session, { carpeta, scope, limit = 50 } = {}) {
  return gdFetch(session, '/gd/me/buzon', {
    params: { carpeta, scope, limit },
  });
}

/** GET /api/v1/gd/dependencias/me/buzon — buzón de mi dependencia. */
export function getBuzonDependencia(session, { carpeta, scope = 'dependencia', limit = 50 } = {}) {
  return gdFetch(session, '/gd/dependencias/me/buzon', {
    params: { carpeta, scope, limit },
  });
}

/** GET /api/v1/gd/dependencias/me/carga-equipo (PERM-REP-009). */
export function getCargaEquipo(session) {
  return gdFetch(session, '/gd/dependencias/me/carga-equipo');
}

/** GET /api/v1/gd/tareas/{id} — ficha de tarea. */
export function getTarea(session, id) {
  return gdFetch(session, `/gd/tareas/${id}`);
}

/**
 * POST /api/v1/gd/tareas/{id}/accion (GD-API-0038) — acciones del workflow.
 * Action ∈ {iniciar, devolver, finalizar, reasignar, escalar}.
 * Reasignar requiere `nuevo_responsable_user_id` + `justificacion`.
 */
export function ejecutarAccionTarea(session, id, accion, payload = {}) {
  return gdFetch(session, `/gd/tareas/${id}/${accion}`, {
    method: 'POST', body: payload,
  });
}

/** GET /api/v1/gd/dependencias/{depId}/usuarios?rol= — selector. */
export function listUsuariosDependencia(session, dependenciaId, { rol } = {}) {
  return gdFetch(
    session,
    `/gd/estructura/dependencias/${dependenciaId}/usuarios`,
    { params: { rol } },
  );
}

/**
 * GET /api/v1/gd/usuarios/{userId}/tareas-pendientes (GD-API-0039).
 * Usado por el wizard de reasignación masiva al inactivar un usuario.
 */
export function getTareasPendientesUsuario(session, userId) {
  return gdFetch(session, `/gd/perfil-usuario/${userId}/tareas-pendientes`);
}

/**
 * POST /api/v1/gd/perfil-usuario/{userId}/tareas/reasignar — lote.
 * body: { tareas: [{id, nuevo_responsable_user_id}], justificacion }
 */
export function reasignarTareasLote(session, userId, payload) {
  return gdFetch(session, `/gd/perfil-usuario/${userId}/tareas/reasignar`, {
    method: 'POST', body: payload,
  });
}

// ─── UI-5: PQRSD (GD-API-0041..0051) ──────────────────────────────────────

/** GET /api/v1/gd/pqrsd con filtros (lista). */
export function listPQRSDFiltrados(session, filtros = {}) {
  return gdFetch(session, '/gd/pqrsd', { params: filtros });
}

/** GET /api/v1/gd/pqrsd/dashboard?dependencia_id=&desde=&hasta= (GD-API-0051). */
export function getPQRSDDashboard(session, { dependencia_id, desde, hasta } = {}) {
  return gdFetch(session, '/gd/pqrsd/dashboard', {
    params: { dependencia_id, desde, hasta },
  });
}

/** GET /api/v1/gd/pqrsd/{id} — ficha completa. */
export function getPQRSD(session, id) {
  return gdFetch(session, `/gd/pqrsd/${id}`);
}

/** POST /api/v1/gd/pqrsd/{id}/asignar-dependencia (GD-API-0044). */
export function asignarDependenciaPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/asignar-dependencia`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/pqrsd/{id}/asignar-funcionario (GD-API-0044). */
export function asignarFuncionarioPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/asignar-funcionario`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/pqrsd/{id}/reasignar (GD-API-0045). */
export function reasignarPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/reasignar`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/pqrsd/{id}/respuestas — proyectar respuesta (GD-API-0046). */
export function proyectarRespuestaPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/respuestas`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/respuestas/{id}/enviar-a-revision (GD-API-0047). */
export function enviarRespuestaARevision(session, respuestaId) {
  return gdFetch(session, `/gd/respuestas/${respuestaId}/enviar-a-revision`, {
    method: 'POST', body: {},
  });
}

/** POST /api/v1/gd/respuestas/{id}/revisar (GD-API-0047). */
export function revisarRespuestaPQRSD(session, respuestaId, payload) {
  return gdFetch(session, `/gd/respuestas/${respuestaId}/revisar`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/respuestas/{id}/aprobar (GD-API-0047). */
export function aprobarRespuestaPQRSD(session, respuestaId, payload = {}) {
  return gdFetch(session, `/gd/respuestas/${respuestaId}/aprobar`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/respuestas/{id}/firmar (GD-API-0047 delega EP-011). */
export function firmarRespuestaPQRSD(session, respuestaId, payload = {}) {
  return gdFetch(session, `/gd/respuestas/${respuestaId}/firmar`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/respuestas/{id}/radicar-salida (GD-API-0047). */
export function radicarSalidaRespuesta(session, respuestaId, payload = {}) {
  return gdFetch(session, `/gd/respuestas/${respuestaId}/radicar-salida`, {
    method: 'POST', body: payload,
  });
}

/** POST /api/v1/gd/respuestas/{id}/enviar (GD-API-0047). */
export function enviarRespuestaPQRSD(session, respuestaId, payload = {}) {
  return gdFetch(session, `/gd/respuestas/${respuestaId}/enviar`, {
    method: 'POST', body: payload,
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
