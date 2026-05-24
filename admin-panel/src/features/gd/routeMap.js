/**
 * Route map del módulo Gestión Documental.
 *
 * Mapea cada path lógico del módulo (lo que `GdSidebar` emite por
 * `onNavigate`) al componente que debe renderizarse. Usado por
 * `GdShellRoute` (en `app/router.jsx`) para resolver el sub-tree
 * `/t/{slug}/gd/*` montado dentro del shell tenant.
 *
 * Convenciones:
 *  - Las claves son rutas relativas al módulo (sin `/gd` prefijo, sin
 *    el slug del tenant). Ej: `''` = landing, `'ventanilla'`,
 *    `'pqrsd'`, `'documentos/:id'`, etc.
 *  - Los componentes se importan desde `features/gd/placeholders` para
 *    aprovechar el wiring rol-aware existente — cada placeholder es
 *    en realidad la vista real (los placeholders se reemplazaron con
 *    componentes 1:1 al cerrar UI-1..UI-15).
 *  - Las rutas con parámetro (`:id`) extraen el último segmento del
 *    path y lo pasan como prop `{nombre}Id` al componente.
 *
 * El resolvedor `resolveGdRoute(subPath)` devuelve:
 *  - `{ Component, extraProps }` cuando hay match
 *  - `{ Component: GdHome, extraProps: {} }` como fallback (landing).
 */
import * as G from './placeholders/index.jsx';

// Rutas estáticas: sin parámetros. El match es exacto contra `subPath`.
const STATIC = Object.freeze({
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
  '/admin/usuarios': G.GdAdminUsuarios,
  '/admin/estructura': G.GdAdminEstructura,
  '/admin/catalogos': G.GdAdminCatalogos,
  '/admin/parametros': G.GdAdminParametros,
  '/admin/calendario': G.GdCalendario,
  '/admin/notificaciones': G.GdPlantillasNotif,
  '/admin/logs': G.GdRetencionLogs,
  '/admin/backup': G.GdBackup,
  '/admin/integraciones': G.GdIntegraciones,
  '/admin/salud': G.GdSaludSistema,
  '/admin/perifericos': G.GdAdminPerifericos,
  '/admin/impresion': G.GdImpresion,
  '/admin/digitalizacion': G.GdDigitalizacion,
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

// Rutas dinámicas: regex → { Component, propName }. El primer grupo de
// captura se pasa al componente como prop con el nombre indicado.
const DYNAMIC = Object.freeze([
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

/**
 * Resuelve un sub-path del módulo GD a `{ Component, extraProps }`.
 *
 * @param {string} subPath - Path relativo al módulo (ej. `'/pqrsd/abc-123'`).
 *   Debe empezar con `/` (o ser cadena vacía para la landing).
 * @returns {{ Component: React.ComponentType, extraProps: object }}
 */
export function resolveGdRoute(subPath) {
  const normalized = subPath || '';
  // 1) match estático exacto
  const StaticCmp = STATIC[normalized];
  if (StaticCmp) {
    return { Component: StaticCmp, extraProps: {} };
  }
  // 2) match dinámico (regex)
  for (const entry of DYNAMIC) {
    const m = normalized.match(entry.re);
    if (m) {
      const extraProps = entry.prop ? { [entry.prop]: m[1] } : {};
      return { Component: entry.Component, extraProps };
    }
  }
  // 3) fallback → landing (GdHome). El usuario ve la home con el
  //    sidebar para reorientarse.
  return { Component: G.GdHome, extraProps: {} };
}

export const _internal = { STATIC, DYNAMIC };
