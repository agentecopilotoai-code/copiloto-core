/**
 * Route map del módulo Gestión Documental.
 *
 * Mapea cada path lógico del módulo a un componente. Usado por
 * `GdShellRoute` (en `app/router.jsx`) para resolver tanto el sub-tree
 * de operación (`/gd/t/{slug}/*`) como el de admin del módulo
 * (`/gd/admin/t/{slug}/*`).
 *
 * Esquema D-ROUTES-01:
 *  - Operación → `OP_STATIC` + `OP_DYNAMIC`.
 *    Sub-paths: `/buzon`, `/pqrsd/mias`, `/documentos/:id`, ...
 *  - Admin del módulo → `ADMIN_STATIC` + `ADMIN_DYNAMIC`.
 *    Sub-paths: `/usuarios`, `/estructura`, `/parametros`, ...
 *    (NO incluyen `/admin/` prefix porque ya está en la URL del shell.)
 *
 * El resolvedor `resolveGdRoute({ mode, subPath })` devuelve:
 *  - `{ Component, extraProps }` cuando hay match
 *  - Fallback: `GdHome` para op, `GdAdminEstructura` para admin (entry
 *    razonable del flujo de configuración del módulo).
 */
import * as G from './placeholders/index.jsx';

// ─── OPERACIÓN ──────────────────────────────────────────────────────────────

const OP_STATIC = Object.freeze({
  '': G.GdHome,
  '/': G.GdHome,
  '/ventanilla': G.GdVentanillaHome,
  '/ventanilla/cola': G.GdColaVU,
  '/ventanilla/nuevo': G.GdNuevoRadicado,
  '/ventanilla/nuevo-salida': G.GdNuevoRadicadoSalida,
  '/ventanilla/anulaciones': G.GdAnulacionesPendientes,
  '/ventanilla/reportes': G.GdReportesVentanilla,
  '/buzon': G.GdBuzonHome,
  '/buzon/dependencia': G.GdBuzonDependencia,
  '/buzon/reasignacion-masiva': G.GdReasignacionMasiva,
  '/pqrsd': G.GdPqrsdPanel,
  '/pqrsd/lista': G.GdPqrsdLista,
  '/pqrsd/mias': G.GdPqrsdMias,
  '/pqrsd/sin-asignar': G.GdPqrsdSinAsignar,
  '/pqrsd/vencimientos': G.GdPqrsdVencimientos,
  '/pqrsd/vencidas': G.GdPqrsdVencidas,
  '/pqrsd/reportes': G.GdPqrsdReportes,
  '/correspondencia/interna': G.GdCorrespondenciaInterna,
  '/correspondencia/externa': G.GdCorrespondenciaExterna,
  '/documentos': G.GdBiblioteca,
  '/plantillas': G.GdPlantillas,
  '/firmas/por-firmar': G.GdPorFirmar,
  '/firmas/firmantes': G.GdAdminFirmantes,
  '/trd': G.GdTrdHome,
  '/tvd': G.GdTvdHome,
  '/expedientes': G.GdExpedientes,
  '/seguridad': G.GdSeguridad,
  '/auditoria': G.GdAuditoria,
  '/auditoria/vista': G.GdVistaAuditor,
  '/reportes': G.GdReportes,
  '/ia/buscar': G.GdBuscarSemantico,
  '/ia/asistente': G.GdAsistente,
  '/ia/pii': G.GdDeteccionPII,
  '/ia/uso': G.GdPanelUsoIA,
  '/ia/config': G.GdConfigModelosIA,
  '/comunicaciones/correo': G.GdCorreoImportado,
  '/comunicaciones/notificaciones': G.GdNotificaciones,
  '/comunicaciones/alertas': G.GdAlertas,
  '/buscar': G.GdBuscar,
  '/consulta': G.GdConsulta,
});

const OP_DYNAMIC = Object.freeze([
  { re: /^\/documentos\/([^/]+)\/generar$/, Component: G.GdGenerarDocumento, prop: 'documentoId' },
  { re: /^\/documentos\/([^/]+)$/, Component: G.GdDocumentoFicha, prop: 'documentoId' },
  { re: /^\/plantillas\/([^/]+)\/generar$/, Component: G.GdGenerarDocumento, prop: 'plantillaId' },
  { re: /^\/pqrsd\/([^/]+)$/, Component: G.GdPqrsdFicha, prop: 'pqrsdId' },
  { re: /^\/correspondencia\/([^/]+)$/, Component: G.GdCorrespondenciaFicha, prop: 'correspondenciaId' },
  { re: /^\/expedientes\/([^/]+)$/, Component: G.GdExpedienteFicha, prop: 'expedienteId' },
  { re: /^\/buzon\/tareas\/([^/]+)$/, Component: G.GdTareaFicha, prop: 'tareaId' },
  { re: /^\/ventanilla\/radicados\/([^/]+)$/, Component: G.GdRadicadoFicha, prop: 'radicadoId' },
  { re: /^\/firmas\/evidencia\/([^/]+)$/, Component: G.GdEvidenciaFirma, prop: 'firmaId' },
  { re: /^\/auditoria\/([^/]+)$/, Component: G.GdAuditoriaEvento, prop: 'eventoId' },
  { re: /^\/trd\/clasificar$/, Component: G.GdClasificarConTRD, prop: null },
]);

// ─── ADMIN DEL MÓDULO ───────────────────────────────────────────────────────

const ADMIN_STATIC = Object.freeze({
  // El landing de admin va a Estructura — paso obligatorio del flujo
  // desde cero (sin versión vigente nada más funciona).
  // Ver docs/gestion documental/FLUJO_DESDE_CERO.md.
  '': G.GdAdminEstructura,
  '/': G.GdAdminEstructura,
  '/usuarios': G.GdAdminUsuarios,
  '/estructura': G.GdAdminEstructura,
  '/catalogos': G.GdAdminCatalogos,
  '/parametros': G.GdAdminParametros,
  '/calendario': G.GdCalendario,
  '/notificaciones': G.GdPlantillasNotif,
  '/logs': G.GdRetencionLogs,
  '/backup': G.GdBackup,
  '/integraciones': G.GdIntegraciones,
  '/salud': G.GdSaludSistema,
  '/perifericos': G.GdAdminPerifericos,
  '/impresion': G.GdImpresion,
  '/digitalizacion': G.GdDigitalizacion,
});

const ADMIN_DYNAMIC = Object.freeze([
  // Slot reservado para detalles dinámicos (ej. ficha de usuario admin).
]);

/**
 * Resuelve un sub-path a `{ Component, extraProps }` según el modo
 * del shell (operación vs admin del módulo).
 *
 * @param {Object} opts
 * @param {'op'|'admin'} opts.mode - Determina cuál tabla de routes consultar.
 * @param {string} opts.subPath - Path relativo al shell (ej. `/buzon`,
 *   `/pqrsd/abc-123`, `/usuarios`).
 * @returns {{ Component: React.ComponentType, extraProps: object }}
 */
export function resolveGdRoute({ mode, subPath }) {
  const STATIC = mode === 'admin' ? ADMIN_STATIC : OP_STATIC;
  const DYNAMIC = mode === 'admin' ? ADMIN_DYNAMIC : OP_DYNAMIC;
  const FALLBACK = mode === 'admin' ? G.GdAdminEstructura : G.GdHome;
  const normalized = subPath || '';
  const StaticCmp = STATIC[normalized];
  if (StaticCmp) return { Component: StaticCmp, extraProps: {} };
  for (const entry of DYNAMIC) {
    const m = normalized.match(entry.re);
    if (m) {
      const extraProps = entry.prop ? { [entry.prop]: m[1] } : {};
      return { Component: entry.Component, extraProps };
    }
  }
  return { Component: FALLBACK, extraProps: {} };
}

export const _internal = { OP_STATIC, OP_DYNAMIC, ADMIN_STATIC, ADMIN_DYNAMIC };
