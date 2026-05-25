/**
 * Cliente API del módulo Gestión Documental.
 *
 * Llama a los endpoints `/v1/gd/*` del backend FastAPI, pasando por el
 * BFF del admin-panel server que reescribe `/admin/api/core/v1/*` a
 * `/v1/*` en el backend. **Mismo prefijo que `coreApi.js`**.
 *
 * BUGFIX (2026-05-25): el `DEFAULT_BASE` original era `/api/v1`
 * (asumía hit directo al backend FastAPI). Pero en deploy local +
 * Docker el browser solo puede llegar al backend a través del BFF —
 * `/api/v1/gd/me` pega al admin-panel server, que no conoce ese path,
 * devuelve 404 silencioso, y la UI muestra "SIN ROL" aunque el user
 * SÍ tenga perfil + roles en la DB. Misma URL base que coreApi
 * (`/admin/api/core/v1`) resuelve el problema para TODOS los
 * endpoints del módulo, no solo `/gd/me`.
 *
 * Convenciones:
 *  - Todos los fetch incluyen `X-Tenant-Id` (resuelto por `session.tenant`).
 *  - `Authorization: Bearer <jwt>` viene del wrapper `authHeaders()`.
 *  - 403 con `code='gd_profile_missing_or_inactive'` → throw `GdNoProfileError`
 *    para que la UI muestre "Solicite activación al administrador".
 */

import { adminPath } from '../../../services/adminSession.js';

const DEFAULT_BASE = '/admin/api/core/v1';

export class GdNoProfileError extends Error {
  constructor(message = 'gd_profile_missing_or_inactive') {
    super(message);
    this.name = 'GdNoProfileError';
    this.code = 'gd_profile_missing_or_inactive';
  }
}

export class GdHttpError extends Error {
  constructor(status, body) {
    super(humanizeGdError(status, body));
    this.status = status;
    this.body = body;
    this.name = 'GdHttpError';
  }
}

/**
 * Traduce un response de error del backend GD a un mensaje legible
 * para el usuario final. Cubre:
 *
 * - 422 Pydantic (lista de `{loc, msg, type}`): "Campo X es requerido"
 *   o "Campo X inválido: ..." según el `type`.
 * - 4xx con shape `{detail: {message, ...}}`: usa `message` directo.
 * - 4xx con shape `{detail: "string"}`: usa el string.
 * - cualquier otro: fallback genérico con el status code.
 *
 * NUNCA expone stack traces ni datos sensibles. El componente que muestra
 * el error puede acceder al body completo via `err.body` si necesita más
 * detalle (ej. para destacar el campo específico).
 */
function humanizeGdError(status, body) {
  if (!body) return `Error HTTP ${status}.`;

  // 422 Pydantic — body.detail es array de {loc, msg, type, input}
  if (status === 422 && Array.isArray(body?.detail)) {
    const campos = body.detail
      .map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.slice(1) : [];  // skip 'body'/'query'
        const nombre = loc.join('.');
        if (d.type === 'missing') {
          return `· Falta el campo "${nombre}"`;
        }
        if (d.msg) {
          return `· Campo "${nombre}": ${d.msg}`;
        }
        return `· Campo "${nombre}" inválido`;
      })
      .join('\n');
    return `Datos incompletos o inválidos:\n${campos}`;
  }

  // 4xx con detail estructurado { code, message }
  if (typeof body?.detail === 'object' && body.detail !== null) {
    const msg = body.detail.message || body.detail.error || JSON.stringify(body.detail);
    return msg;
  }

  // 4xx con detail string plano
  if (typeof body?.detail === 'string') {
    return body.detail;
  }

  // Fallback
  return `Error HTTP ${status}.`;
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
  // adminPath() prepende `VITE_ADMIN_BACKEND_ORIGIN` cuando el SPA
  // se sirve desde un origin distinto al admin-panel (dev con vite
  // server proxy, etc). En el deploy normal devuelve el path tal cual.
  return adminPath(`${base}${path}`);
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

/** GET /v1/gd/buzon — buzón del usuario actual (filtros opcionales).
 *
 * Backend canónico: `/gd/buzon` (sin sub-recurso `/dependencias/me/`).
 * El `carpeta` / `scope` se pasan como query params; los handlers ignoran
 * los que no entiendan — defensa contra evolución del API.
 */
export function getBuzonDependencia(session, { carpeta, scope = 'dependencia', limit = 50 } = {}) {
  return gdFetch(session, '/gd/buzon', {
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

// ─── UI-6: PQRSD cierre + traslado + suspensión + reportes ────────────────

/** POST /gd/pqrsd/{id}/cerrar (GD-API-0048). */
export function cerrarPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/cerrar`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/pqrsd/{id}/reabrir (GD-API-0048). */
export function reabrirPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/reabrir`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/pqrsd/{id}/trasladar-competencia (GD-API-0049). */
export function trasladarPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/trasladar-competencia`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/pqrsd/{id}/solicitar-info-adicional (GD-API-0050). */
export function solicitarInfoAdicionalPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/solicitar-info-adicional`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/pqrsd/{id}/suspender (GD-API-0042). */
export function suspenderTerminoPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/suspender`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/pqrsd/{id}/reanudar (GD-API-0042). */
export function reanudarTerminoPQRSD(session, id, payload) {
  return gdFetch(session, `/gd/pqrsd/${id}/reanudar`, {
    method: 'POST', body: payload,
  });
}

/** GET /gd/pqrsd/{id}/suspensiones — historial de suspensiones del término. */
export function listSuspensionesPQRSD(session, id) {
  return gdFetch(session, `/gd/pqrsd/${id}/suspensiones`);
}

/** GET /gd/pqrsd/reportes — tableros agregados (KPIs por dep/tipo/canal/tiempos). */
export function getReportesPQRSD(session, { desde, hasta, dependencia_id } = {}) {
  return gdFetch(session, '/gd/pqrsd/reportes', {
    params: { desde, hasta, dependencia_id },
  });
}

/** POST /gd/pqrsd/reportes/exportar — encola export (PERM-REP-004). */
export function exportarReportePQRSD(session, { formato = 'csv', desde, hasta } = {}) {
  return gdFetch(session, '/gd/pqrsd/reportes/exportar', {
    method: 'POST', body: { formato, desde, hasta },
  });
}

// ─── UI-7: Correspondencia interna + externa (GD-API-0052..0056) ──────────

/** POST /gd/correspondencia/interna (GD-API-0052). */
export function crearCorrespondenciaInterna(session, payload) {
  return gdFetch(session, '/gd/correspondencia/interna', {
    method: 'POST', body: payload,
  });
}

/** GET /gd/correspondencia con filtros (tipo, bandeja, scope). */
export function listCorrespondencia(session, filtros = {}) {
  return gdFetch(session, '/gd/correspondencia', { params: filtros });
}

/** GET /gd/correspondencia/{id} — ficha. */
export function getCorrespondencia(session, id) {
  return gdFetch(session, `/gd/correspondencia/${id}`);
}

/** POST /gd/correspondencia/{id}/marcar-leida (GD-API-0052). */
export function marcarLeidaCorrespondencia(session, id) {
  return gdFetch(session, `/gd/correspondencia/${id}/marcar-leida`, {
    method: 'POST', body: {},
  });
}

/** POST /gd/correspondencia/{id}/responder. */
export function responderCorrespondencia(session, id, payload) {
  return gdFetch(session, `/gd/correspondencia/${id}/responder`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/correspondencia/{id}/reenviar. */
export function reenviarCorrespondencia(session, id, payload) {
  return gdFetch(session, `/gd/correspondencia/${id}/reenviar`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/correspondencia/externa/borrador (GD-API-0054). */
export function crearBorradorCorrespondenciaExterna(session, payload) {
  return gdFetch(session, '/gd/correspondencia/externa/borrador', {
    method: 'POST', body: payload,
  });
}

/** Workflow CE — enviar a revisión. */
export function enviarCorrespondenciaARevision(session, id) {
  return gdFetch(session, `/gd/correspondencia/${id}/enviar-a-revision`, {
    method: 'POST', body: {},
  });
}

/** Workflow CE — revisar. */
export function revisarCorrespondencia(session, id, payload) {
  return gdFetch(session, `/gd/correspondencia/${id}/revisar`, {
    method: 'POST', body: payload,
  });
}

/** Workflow CE — aprobar. */
export function aprobarCorrespondencia(session, id, payload = {}) {
  return gdFetch(session, `/gd/correspondencia/${id}/aprobar`, {
    method: 'POST', body: payload,
  });
}

/** Workflow CE — firmar. */
export function firmarCorrespondencia(session, id, payload = {}) {
  return gdFetch(session, `/gd/correspondencia/${id}/firmar`, {
    method: 'POST', body: payload,
  });
}

/** Workflow CE — radicar salida. */
export function radicarSalidaCorrespondencia(session, id, payload = {}) {
  return gdFetch(session, `/gd/correspondencia/${id}/radicar-salida`, {
    method: 'POST', body: payload,
  });
}

/** Workflow CE — enviar al destinatario externo. */
export function enviarCorrespondencia(session, id, payload = {}) {
  return gdFetch(session, `/gd/correspondencia/${id}/enviar`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/correspondencia/{id}/registrar-soporte-envio (GD-API-0054, PERM-CE-011). */
export function registrarSoporteEnvio(session, id, payload) {
  return gdFetch(session, `/gd/correspondencia/${id}/registrar-soporte-envio`, {
    method: 'POST', body: payload,
  });
}

/** POST /gd/correspondencia/{id}/destinatarios — agregar (GD-API-0055). */
export function agregarDestinatarioCorrespondencia(session, id, payload) {
  return gdFetch(session, `/gd/correspondencia/${id}/destinatarios`, {
    method: 'POST', body: payload,
  });
}

/** DELETE /gd/correspondencia/{id}/destinatarios/{destId} — quitar. */
export function quitarDestinatarioCorrespondencia(session, id, destId) {
  return gdFetch(session, `/gd/correspondencia/${id}/destinatarios/${destId}`, {
    method: 'DELETE',
  });
}

/** POST /gd/correspondencia/{id}/anular (GD-API-0056). */
export function solicitarAnulacionCorrespondencia(session, id, motivo) {
  return gdFetch(session, `/gd/correspondencia/${id}/anular`, {
    method: 'POST', body: { motivo },
  });
}

// ─── UI-8: Documentos + Plantillas + Firmas (GD-API-0057..0072) ──────────

// --- Documentos ---
export function listDocumentos(session, filtros = {}) {
  return gdFetch(session, '/gd/documentos', { params: filtros });
}
export function getDocumento(session, id) {
  return gdFetch(session, `/gd/documentos/${id}`);
}
export function listVersionesDocumento(session, id) {
  return gdFetch(session, `/gd/documentos/${id}/versiones`);
}
export function crearDocumento(session, payload) {
  return gdFetch(session, '/gd/documentos', {
    method: 'POST', body: payload,
  });
}
export function nuevaVersionDocumento(session, id, payload) {
  return gdFetch(session, `/gd/documentos/${id}/versiones`, {
    method: 'POST', body: payload,
  });
}
export function anularDocumento(session, id, motivo) {
  return gdFetch(session, `/gd/documentos/${id}/anular`, {
    method: 'POST', body: { motivo },
  });
}
export function subirArchivo(session, payload) {
  return gdFetch(session, '/core/archivos', {
    method: 'POST', body: payload,
  });
}

// --- Plantillas ---
export function listPlantillas(session, filtros = {}) {
  return gdFetch(session, '/gd/plantillas', { params: filtros });
}
export function getPlantilla(session, id) {
  return gdFetch(session, `/gd/plantillas/${id}`);
}
export function crearPlantilla(session, payload) {
  return gdFetch(session, '/gd/plantillas', {
    method: 'POST', body: payload,
  });
}
export function actualizarPlantilla(session, id, payload) {
  return gdFetch(session, `/gd/plantillas/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function nuevaVersionPlantilla(session, id, payload) {
  return gdFetch(session, `/gd/plantillas/${id}/versiones`, {
    method: 'POST', body: payload,
  });
}
export function inactivarPlantilla(session, id, motivo) {
  return gdFetch(session, `/gd/plantillas/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}
export function generarDocumentoDePlantilla(session, id, variables) {
  return gdFetch(session, `/gd/plantillas/${id}/generar`, {
    method: 'POST', body: { variables },
  });
}

// --- Firmas ---
export function listPorFirmar(session, filtros = {}) {
  return gdFetch(session, '/gd/firmas/por-firmar', { params: filtros });
}
export function getEvidenciaFirma(session, firmaId) {
  return gdFetch(session, `/gd/firmas/${firmaId}/evidencia`);
}
export function registrarFirmaEscaneada(session, documentoId, payload) {
  return gdFetch(session, `/gd/firmas/${documentoId}/escaneada`, {
    method: 'POST', body: payload,
  });
}
export function firmarDocumento(session, documentoId, payload = {}) {
  return gdFetch(session, `/gd/firmas/${documentoId}/firmar`, {
    method: 'POST', body: payload,
  });
}
export function rechazarFirmaDocumento(session, documentoId, motivo) {
  return gdFetch(session, `/gd/firmas/${documentoId}/rechazar`, {
    method: 'POST', body: { motivo },
  });
}
export function listFirmantesAutorizados(session) {
  return gdFetch(session, '/gd/firmantes-autorizados');
}
export function crearFirmanteAutorizado(session, payload) {
  return gdFetch(session, '/gd/firmantes-autorizados', {
    method: 'POST', body: payload,
  });
}
export function actualizarFirmanteAutorizado(session, id, payload) {
  return gdFetch(session, `/gd/firmantes-autorizados/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function inactivarFirmanteAutorizado(session, id, motivo) {
  return gdFetch(session, `/gd/firmantes-autorizados/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}

// ─── UI-9: TRD/TVD + Expediente Electrónico (GD-API-0073..0085) ──────────

// --- TRD (Tabla de Retención Documental) ---
export function listTRD(session, filtros = {}) {
  return gdFetch(session, '/gd/trd', { params: filtros });
}
export function getSerie(session, id) {
  return gdFetch(session, `/gd/trd/series/${id}`);
}
export function getTRDVersionActual(session) {
  return gdFetch(session, '/gd/trd/version-actual');
}
export function listVersionesTRD(session) {
  return gdFetch(session, '/gd/trd/versiones');
}
export function crearSerie(session, payload) {
  return gdFetch(session, '/gd/trd/series', {
    method: 'POST', body: payload,
  });
}
export function actualizarSerie(session, id, payload) {
  return gdFetch(session, `/gd/trd/series/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function eliminarSerie(session, id, motivo) {
  return gdFetch(session, `/gd/trd/series/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}
export function crearSubserie(session, serieId, payload) {
  return gdFetch(session, `/gd/trd/series/${serieId}/subseries`, {
    method: 'POST', body: payload,
  });
}
export function crearTipoDocumental(session, subserieId, payload) {
  return gdFetch(session, `/gd/trd/subseries/${subserieId}/tipos`, {
    method: 'POST', body: payload,
  });
}
export function nuevaVersionTRD(session, payload) {
  return gdFetch(session, '/gd/trd/versiones', {
    method: 'POST', body: payload,
  });
}
export function aprobarVersionTRD(session, versionId, payload) {
  return gdFetch(session, `/gd/trd/versiones/${versionId}/aprobar`, {
    method: 'POST', body: payload,
  });
}

// --- TVD ---
export function listTVD(session, filtros = {}) {
  return gdFetch(session, '/gd/tvd', { params: filtros });
}
export function actualizarTVD(session, id, payload) {
  return gdFetch(session, `/gd/tvd/${id}`, {
    method: 'PATCH', body: payload,
  });
}

// --- Clasificación documental ---
export function clasificarConTRD(session, payload) {
  return gdFetch(session, '/gd/trd/clasificar', {
    method: 'POST', body: payload,
  });
}

// --- Expedientes electrónicos ---
export function listExpedientes(session, filtros = {}) {
  return gdFetch(session, '/gd/expedientes', { params: filtros });
}
export function getExpediente(session, id) {
  return gdFetch(session, `/gd/expedientes/${id}`);
}
export function crearExpediente(session, payload) {
  return gdFetch(session, '/gd/expedientes', {
    method: 'POST', body: payload,
  });
}
export function actualizarExpediente(session, id, payload) {
  return gdFetch(session, `/gd/expedientes/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function listDocumentosExpediente(session, id) {
  return gdFetch(session, `/gd/expedientes/${id}/documentos`);
}
export function agregarDocumentoExpediente(session, id, documentoId) {
  return gdFetch(session, `/gd/expedientes/${id}/documentos`, {
    method: 'POST', body: { documento_id: documentoId },
  });
}
export function quitarDocumentoExpediente(session, id, documentoId, motivo) {
  return gdFetch(session, `/gd/expedientes/${id}/documentos/${documentoId}`, {
    method: 'DELETE', body: { motivo },
  });
}
export function cerrarExpediente(session, id, payload) {
  return gdFetch(session, `/gd/expedientes/${id}/cerrar`, {
    method: 'POST', body: payload,
  });
}
export function transferirExpediente(session, id, payload) {
  return gdFetch(session, `/gd/expedientes/${id}/transferir`, {
    method: 'POST', body: payload,
  });
}
export function reabrirExpediente(session, id, motivo) {
  return gdFetch(session, `/gd/expedientes/${id}/reabrir`, {
    method: 'POST', body: { motivo },
  });
}
export function getIndiceExpediente(session, id) {
  return gdFetch(session, `/gd/expedientes/${id}/indice`);
}
export function getActaCierreExpediente(session, id) {
  return gdFetch(session, `/gd/expedientes/${id}/acta-cierre`);
}
export function buscarExpedientes(session, filtros = {}) {
  return gdFetch(session, '/gd/expedientes/buscar', { params: filtros });
}

// ─── UI-10: Admin del sistema GD (GD-API-0086..0115) ─────────────────────
//
// Paths canónicos backend: `/gd/perfil-usuario/*` y `/gd/usuarios/{id}/roles`.
// El UI llama estos wrappers (que mantienen los nombres "lindos" de la UX)
// pero internamente apuntan a las rutas REST que el backend efectivamente
// expone — sin esto, todos los endpoints daban 404.

// --- Usuarios GD ---
export function listUsuariosGd(session, filtros = {}) {
  return gdFetch(session, '/gd/perfil-usuario', { params: filtros });
}
export function getUsuarioGd(session, id) {
  return gdFetch(session, `/gd/perfil-usuario/${id}`);
}
export function crearUsuarioGd(session, payload) {
  return gdFetch(session, '/gd/perfil-usuario', {
    method: 'POST', body: payload,
  });
}
export function actualizarUsuarioGd(session, id, payload) {
  return gdFetch(session, `/gd/perfil-usuario/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function asignarRolUsuarioGd(session, id, payload) {
  return gdFetch(session, `/gd/usuarios/${id}/roles`, {
    method: 'POST', body: payload,
  });
}
export function removerRolUsuarioGd(session, id, asignacionId, motivo) {
  // Backend usa el id de la asignación (asignacion_alcance_id), NO el rol_codigo.
  // El caller debe pasar `asignacionId` (que viene en `roles_gd_vigentes[].asignacion_alcance_id`).
  return gdFetch(session, `/gd/usuarios/${id}/roles/${asignacionId}/cerrar`, {
    method: 'POST', body: { motivo },
  });
}
export function inactivarUsuarioGd(session, id, motivo) {
  return gdFetch(session, `/gd/perfil-usuario/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}
export function reactivarUsuarioGd(session, id, motivo) {
  return gdFetch(session, `/gd/perfil-usuario/${id}/reactivar`, {
    method: 'POST', body: { motivo },
  });
}

// --- Estructura orgánica ---
// Backend canónico: `/gd/admin/estructura/vigente` (devuelve el árbol
// completo de la versión activa). El path plano `/gd/admin/estructura`
// NO existe. Si hay más de una versión, usar `/gd/admin/estructura/versiones`.
export function getEstructuraOrganica(session) {
  return gdFetch(session, '/gd/admin/estructura/vigente');
}
/**
 * Crear primera versión (o nueva versión) de la estructura orgánica.
 * Sin una versión vigente, NO se puede crear ninguna dependencia
 * (DependenciaCreate.version_estructura_id es required).
 *
 * Schema backend: VersionEstructuraCreate
 *   - numero_version: string (1..40)  — ej. "v1", "2026", "Decreto-001"
 *   - descripcion: string? (≤2000)
 *   - acto_administrativo: string? (≤500) — ej. "Decreto 001 de 2026"
 *   - fecha_inicio_vigencia: ISO date
 */
export function crearVersionEstructura(session, payload) {
  return gdFetch(session, '/gd/admin/estructura/versiones', {
    method: 'POST', body: payload,
  });
}
export function crearDependencia(session, payload) {
  return gdFetch(session, '/gd/admin/dependencias', {
    method: 'POST', body: payload,
  });
}
export function actualizarDependencia(session, id, payload) {
  return gdFetch(session, `/gd/admin/dependencias/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function reubicarDependencia(session, id, nuevoPadreId, motivo) {
  return gdFetch(session, `/gd/admin/dependencias/${id}/reubicar`, {
    method: 'POST', body: { nuevo_padre_id: nuevoPadreId, motivo },
  });
}
export function inactivarDependencia(session, id, motivo) {
  return gdFetch(session, `/gd/admin/dependencias/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}

// --- Catálogos ---
export function listCatalogos(session) {
  return gdFetch(session, '/gd/admin/catalogos');
}
export function listItemsCatalogo(session, codigo) {
  return gdFetch(session, `/gd/admin/catalogos/${codigo}`);
}
export function crearItemCatalogo(session, codigo, payload) {
  return gdFetch(session, `/gd/admin/catalogos/${codigo}`, {
    method: 'POST', body: payload,
  });
}
export function actualizarItemCatalogo(session, codigo, itemId, payload) {
  return gdFetch(session, `/gd/admin/catalogos/${codigo}/${itemId}`, {
    method: 'PATCH', body: payload,
  });
}
export function inactivarItemCatalogo(session, codigo, itemId, motivo) {
  return gdFetch(session, `/gd/admin/catalogos/${codigo}/${itemId}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}

// --- Parámetros ---
export function listParametros(session) {
  return gdFetch(session, '/gd/admin/parametros');
}
export function actualizarParametro(session, codigo, payload) {
  return gdFetch(session, `/gd/admin/parametros/${codigo}`, {
    method: 'PATCH', body: payload,
  });
}

// --- Calendario laboral ---
export function getCalendarioLaboral(session, anio) {
  return gdFetch(session, '/gd/admin/calendario', { params: { anio } });
}
export function agregarDiaFestivo(session, payload) {
  return gdFetch(session, '/gd/admin/calendario/festivos', {
    method: 'POST', body: payload,
  });
}
export function quitarDiaFestivo(session, id, motivo) {
  return gdFetch(session, `/gd/admin/calendario/festivos/${id}`, {
    method: 'DELETE', body: { motivo },
  });
}

// --- Plantillas de notificación ---
export function listPlantillasNotificacion(session) {
  return gdFetch(session, '/gd/admin/notificaciones/plantillas');
}
export function actualizarPlantillaNotificacion(session, codigo, payload) {
  return gdFetch(session, `/gd/admin/notificaciones/plantillas/${codigo}`, {
    method: 'PATCH', body: payload,
  });
}
export function probarPlantillaNotificacion(session, codigo, payload) {
  return gdFetch(session, `/gd/admin/notificaciones/plantillas/${codigo}/probar`, {
    method: 'POST', body: payload,
  });
}

// --- Política de retención de logs ---
export function getPoliticaRetencionLogs(session) {
  return gdFetch(session, '/gd/admin/logs/retencion');
}
export function actualizarPoliticaRetencionLogs(session, payload) {
  return gdFetch(session, '/gd/admin/logs/retencion', {
    method: 'PATCH', body: payload,
  });
}

// --- Backup / restauración ---
export function getEstadoBackups(session) {
  return gdFetch(session, '/gd/admin/backups');
}
export function dispararBackupManual(session, motivo) {
  return gdFetch(session, '/gd/admin/backups/manual', {
    method: 'POST', body: { motivo },
  });
}

// --- Integraciones externas ---
export function listIntegraciones(session) {
  return gdFetch(session, '/gd/admin/integraciones');
}
export function actualizarIntegracion(session, codigo, payload) {
  return gdFetch(session, `/gd/admin/integraciones/${codigo}`, {
    method: 'PATCH', body: payload,
  });
}
export function probarIntegracion(session, codigo) {
  return gdFetch(session, `/gd/admin/integraciones/${codigo}/probar`, {
    method: 'POST',
  });
}

// --- Seguridad ---
export function getConfigSeguridad(session) {
  return gdFetch(session, '/gd/admin/seguridad');
}
export function actualizarConfigSeguridad(session, payload) {
  return gdFetch(session, '/gd/admin/seguridad', {
    method: 'PATCH', body: payload,
  });
}
export function listSesionesActivas(session, filtros = {}) {
  return gdFetch(session, '/gd/admin/seguridad/sesiones', { params: filtros });
}
export function revocarSesion(session, sessionId, motivo) {
  return gdFetch(session, `/gd/admin/seguridad/sesiones/${sessionId}`, {
    method: 'DELETE', body: { motivo },
  });
}

// --- Salud del sistema ---
export function getSaludSistema(session) {
  return gdFetch(session, '/gd/admin/salud');
}

// ─── UI-11: Auditoría + Reportes consolidados (GD-API-0116..0125) ────────

// --- Auditoría ---
// Backend canónico: `/core/auditoria` (schema transversal `core.evento_auditoria`).
// NO `/gd/auditoria` — la auditoría es shared service del core, no del módulo GD.
// Ver `infra/postgres/modules/gd.sql` § 1 y `app/gd/routes.py` router_core.
export function buscarAuditoria(session, filtros = {}) {
  return gdFetch(session, '/core/auditoria', { params: filtros });
}
export function getEventoAuditoria(session, id) {
  return gdFetch(session, `/core/auditoria/${id}`);
}
export function exportarAuditoria(session, payload) {
  // Backend usa /gd/reportes/auditoria/exportar (módulo GD-specific reporting).
  return gdFetch(session, '/gd/reportes/auditoria/exportar', {
    method: 'POST', body: payload,
  });
}
export function listCatalogoEntidadesAuditoria(session) {
  // Reutilizamos el catálogo de eventos del core — la UI extrae las
  // entidades distintas client-side (el catálogo tiene { evento, entidad_tipo }).
  return gdFetch(session, '/core/auditoria/catalogo-eventos');
}
export function listCatalogoAccionesAuditoria(session) {
  return gdFetch(session, '/core/auditoria/catalogo-eventos');
}

// --- Reportes consolidados ---
export function getReportesConsolidados(session, filtros = {}) {
  return gdFetch(session, '/gd/reportes/consolidados', { params: filtros });
}
export function exportarReporteConsolidado(session, payload) {
  return gdFetch(session, '/gd/reportes/consolidados/exportar', {
    method: 'POST', body: payload,
  });
}
export function exportarReporteEjecutivoPdf(session, payload) {
  return gdFetch(session, '/gd/reportes/ejecutivo/pdf', {
    method: 'POST', body: payload,
  });
}

// --- Auditor: integridad de registros ---
export function getResumenIntegridadAuditor(session) {
  return gdFetch(session, '/gd/auditor/integridad');
}
export function verificarHashRegistro(session, entidadTipo, entidadId) {
  return gdFetch(session, `/gd/auditor/integridad/${entidadTipo}/${entidadId}`);
}

// ─── UI-12: IA embebida (GD-API-0126..0140) ──────────────────────────────

// --- Sugerencia de clasificación (TRD + tipo + dependencia) ---
export function sugerirClasificacionIA(session, payload) {
  return gdFetch(session, '/gd/ia/clasificacion/sugerir', {
    method: 'POST', body: payload,
  });
}
export function feedbackSugerenciaClasificacionIA(session, sugerenciaId, payload) {
  return gdFetch(session, `/gd/ia/clasificacion/sugerencias/${sugerenciaId}/feedback`, {
    method: 'POST', body: payload,
  });
}

// --- Resumen automático ---
export function generarResumenIA(session, payload) {
  return gdFetch(session, '/gd/ia/resumen', {
    method: 'POST', body: payload,
  });
}

// --- Búsqueda semántica ---
export function buscarSemanticoIA(session, payload) {
  return gdFetch(session, '/gd/ia/busqueda-semantica', {
    method: 'POST', body: payload,
  });
}

// --- Asistente conversacional ---
export function enviarMensajeAsistenteIA(session, payload) {
  return gdFetch(session, '/gd/ia/asistente/mensajes', {
    method: 'POST', body: payload,
  });
}
export function listConversacionesAsistente(session) {
  return gdFetch(session, '/gd/ia/asistente/conversaciones');
}
export function getConversacionAsistente(session, id) {
  return gdFetch(session, `/gd/ia/asistente/conversaciones/${id}`);
}

// --- Detección de PII (Ley 1581/2012) ---
export function detectarPiiIA(session, payload) {
  return gdFetch(session, '/gd/ia/pii/detectar', {
    method: 'POST', body: payload,
  });
}
export function listAlertasPii(session, filtros = {}) {
  return gdFetch(session, '/gd/ia/pii/alertas', { params: filtros });
}
export function marcarAlertaPiiAtendida(session, id, payload) {
  return gdFetch(session, `/gd/ia/pii/alertas/${id}/atender`, {
    method: 'POST', body: payload,
  });
}

// --- Uso + costos ---
export function getUsoIA(session, filtros = {}) {
  return gdFetch(session, '/gd/ia/uso', { params: filtros });
}

// --- Configuración de modelos ---
export function getConfigModelosIA(session) {
  return gdFetch(session, '/gd/ia/config');
}
export function actualizarConfigModelosIA(session, payload) {
  return gdFetch(session, '/gd/ia/config', {
    method: 'PATCH', body: payload,
  });
}

// ─── UI-13: Correo + notificaciones + alertas (GD-API-0141..0156) ────────

// --- Correo institucional importado ---
export function listCorreosImportados(session, filtros = {}) {
  return gdFetch(session, '/gd/correo/importados', { params: filtros });
}
export function getCorreoImportado(session, id) {
  return gdFetch(session, `/gd/correo/importados/${id}`);
}
export function convertirCorreoARadicado(session, id, payload) {
  return gdFetch(session, `/gd/correo/importados/${id}/convertir-radicado`, {
    method: 'POST', body: payload,
  });
}
export function descartarCorreo(session, id, motivo) {
  return gdFetch(session, `/gd/correo/importados/${id}/descartar`, {
    method: 'POST', body: { motivo },
  });
}

// --- Notificaciones internas (per-usuario) ---
export function listMisNotificaciones(session, filtros = {}) {
  return gdFetch(session, '/gd/me/notificaciones', { params: filtros });
}
export function marcarNotificacionLeida(session, id) {
  return gdFetch(session, `/gd/me/notificaciones/${id}/leida`, {
    method: 'POST',
  });
}
export function marcarTodasNotificacionesLeidas(session) {
  return gdFetch(session, '/gd/me/notificaciones/marcar-todas-leidas', {
    method: 'POST',
  });
}
export function getPreferenciasNotificaciones(session) {
  return gdFetch(session, '/gd/me/notificaciones/preferencias');
}
export function actualizarPreferenciasNotificaciones(session, payload) {
  return gdFetch(session, '/gd/me/notificaciones/preferencias', {
    method: 'PATCH', body: payload,
  });
}

// --- Alertas operacionales ---
export function listAlertas(session, filtros = {}) {
  return gdFetch(session, '/gd/alertas', { params: filtros });
}
export function atenderAlerta(session, id, payload) {
  return gdFetch(session, `/gd/alertas/${id}/atender`, {
    method: 'POST', body: payload,
  });
}
export function listReglasAlerta(session) {
  return gdFetch(session, '/gd/alertas/reglas');
}
export function crearReglaAlerta(session, payload) {
  return gdFetch(session, '/gd/alertas/reglas', {
    method: 'POST', body: payload,
  });
}
export function actualizarReglaAlerta(session, id, payload) {
  return gdFetch(session, `/gd/alertas/reglas/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function inactivarReglaAlerta(session, id, motivo) {
  return gdFetch(session, `/gd/alertas/reglas/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}

// ─── UI-14/UI-15: Periféricos (GD-API-0157..0173) ─────────────────────────

// --- Admin periféricos ---
export function listPerifericos(session, filtros = {}) {
  return gdFetch(session, '/gd/perifericos', { params: filtros });
}
export function getPeriferico(session, id) {
  return gdFetch(session, `/gd/perifericos/${id}`);
}
export function crearPeriferico(session, payload) {
  return gdFetch(session, '/gd/perifericos', {
    method: 'POST', body: payload,
  });
}
export function actualizarPeriferico(session, id, payload) {
  return gdFetch(session, `/gd/perifericos/${id}`, {
    method: 'PATCH', body: payload,
  });
}
export function inactivarPeriferico(session, id, motivo) {
  return gdFetch(session, `/gd/perifericos/${id}/inactivar`, {
    method: 'POST', body: { motivo },
  });
}
export function getEstadoPerifericos(session) {
  // Backend NO tiene `/perifericos/estado` — el handler `/{periferico_id}`
  // interpreta "estado" como UUID y devuelve 422. El listado real es
  // `GET /gd/perifericos` (con filtros opcionales por query param);
  // el "estado" en la UI se calcula client-side desde los items.
  return gdFetch(session, '/gd/perifericos');
}

// --- Impresión ---
export function imprimirEtiqueta(session, payload) {
  return gdFetch(session, '/gd/perifericos/imprimir/etiqueta', {
    method: 'POST', body: payload,
  });
}
export function imprimirConstancia(session, payload) {
  return gdFetch(session, '/gd/perifericos/imprimir/constancia', {
    method: 'POST', body: payload,
  });
}
export function reimprimir(session, trabajoId, motivo) {
  return gdFetch(session, `/gd/perifericos/imprimir/${trabajoId}/reimprimir`, {
    method: 'POST', body: { motivo },
  });
}
export function listTrabajosImpresion(session, filtros = {}) {
  return gdFetch(session, '/gd/perifericos/trabajos-impresion', { params: filtros });
}

// --- Digitalización ---
export function digitalizarIndividual(session, payload) {
  return gdFetch(session, '/gd/perifericos/digitalizar/individual', {
    method: 'POST', body: payload,
  });
}
export function digitalizarLote(session, payload) {
  return gdFetch(session, '/gd/perifericos/digitalizar/lote', {
    method: 'POST', body: payload,
  });
}
export function listColaDigitalizacion(session, filtros = {}) {
  return gdFetch(session, '/gd/perifericos/digitalizar/cola', { params: filtros });
}
export function asociarDigitalizacionARadicado(session, payload) {
  return gdFetch(session, '/gd/perifericos/digitalizar/asociar', {
    method: 'POST', body: payload,
  });
}
export function reemplazarDigitalizacion(session, digitalizacionId, payload) {
  return gdFetch(session, `/gd/perifericos/digitalizar/${digitalizacionId}/reemplazar`, {
    method: 'POST', body: payload,
  });
}

// Internal exports for testing.
export const _internal = { gdPath, gdFetch, authHeaders };
