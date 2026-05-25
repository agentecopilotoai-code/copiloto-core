import { describe, it, expect } from 'vitest';

import { resolveGdRoute, _internal } from './routeMap.js';
import * as G from './placeholders/index.jsx';

// helpers para reducir verbosidad
const op = (subPath) => resolveGdRoute({ mode: 'op', subPath });
const adm = (subPath) => resolveGdRoute({ mode: 'admin', subPath });

describe('resolveGdRoute — operación', () => {
  it('landing → GdHome para cadena vacía', () => {
    const r = op('');
    expect(r.Component).toBe(G.GdHome);
    expect(r.extraProps).toEqual({});
  });

  it('landing → GdHome para "/"', () => {
    expect(op('/').Component).toBe(G.GdHome);
  });

  it('match estático exacto', () => {
    expect(op('/ventanilla').Component).toBe(G.GdVentanillaHome);
    expect(op('/pqrsd').Component).toBe(G.GdPqrsdPanel);
    expect(op('/documentos').Component).toBe(G.GdBiblioteca);
    expect(op('/plantillas').Component).toBe(G.GdPlantillas);
    expect(op('/trd').Component).toBe(G.GdTrdHome);
    expect(op('/expedientes').Component).toBe(G.GdExpedientes);
    expect(op('/auditoria').Component).toBe(G.GdAuditoria);
    expect(op('/reportes').Component).toBe(G.GdReportes);
    expect(op('/seguridad').Component).toBe(G.GdSeguridad);
    expect(op('/ia/asistente').Component).toBe(G.GdAsistente);
    expect(op('/comunicaciones/notificaciones').Component).toBe(G.GdNotificaciones);
  });

  it('match dinámico: ficha de documento con UUID', () => {
    const r = op('/documentos/abc-123-uuid');
    expect(r.Component).toBe(G.GdDocumentoFicha);
    expect(r.extraProps).toEqual({ documentoId: 'abc-123-uuid' });
  });

  it('match dinámico: generar documento desde plantilla', () => {
    const r = op('/plantillas/p1/generar');
    expect(r.Component).toBe(G.GdGenerarDocumento);
    expect(r.extraProps).toEqual({ plantillaId: 'p1' });
  });

  it('match dinámico: ficha PQRSD', () => {
    const r = op('/pqrsd/p-2026-1');
    expect(r.Component).toBe(G.GdPqrsdFicha);
    expect(r.extraProps).toEqual({ pqrsdId: 'p-2026-1' });
  });

  it('match dinámico: ficha de expediente', () => {
    const r = op('/expedientes/exp-001');
    expect(r.Component).toBe(G.GdExpedienteFicha);
    expect(r.extraProps).toEqual({ expedienteId: 'exp-001' });
  });

  it('match dinámico: tarea del buzón', () => {
    const r = op('/buzon/tareas/t1');
    expect(r.Component).toBe(G.GdTareaFicha);
    expect(r.extraProps).toEqual({ tareaId: 't1' });
  });

  it('match dinámico: ficha radicado', () => {
    const r = op('/ventanilla/radicados/r-2026-100');
    expect(r.Component).toBe(G.GdRadicadoFicha);
    expect(r.extraProps).toEqual({ radicadoId: 'r-2026-100' });
  });

  it('match dinámico: correspondencia ficha', () => {
    const r = op('/correspondencia/c1');
    expect(r.Component).toBe(G.GdCorrespondenciaFicha);
    expect(r.extraProps).toEqual({ correspondenciaId: 'c1' });
  });

  it('match dinámico: evidencia de firma', () => {
    const r = op('/firmas/evidencia/f1');
    expect(r.Component).toBe(G.GdEvidenciaFirma);
    expect(r.extraProps).toEqual({ firmaId: 'f1' });
  });

  it('match dinámico: evento de auditoría', () => {
    const r = op('/auditoria/e1');
    expect(r.Component).toBe(G.GdAuditoriaEvento);
    expect(r.extraProps).toEqual({ eventoId: 'e1' });
  });

  it('match dinámico: clasificar con TRD (sin propId)', () => {
    const r = op('/trd/clasificar');
    expect(r.Component).toBe(G.GdClasificarConTRD);
    expect(r.extraProps).toEqual({});
  });

  it('fallback → GdHome para path desconocido', () => {
    expect(op('/nope/no/existe').Component).toBe(G.GdHome);
  });

  it('fallback → GdHome para subPath undefined', () => {
    expect(op(undefined).Component).toBe(G.GdHome);
  });

  it('routes admin NO se resuelven en mode=op (aislamiento)', () => {
    // `/usuarios` solo existe en ADMIN_STATIC. En op debe caer al fallback.
    expect(op('/usuarios').Component).toBe(G.GdHome);
  });
});

describe('resolveGdRoute — admin del módulo', () => {
  it('landing admin → Estructura (entry razonable del flujo desde cero)', () => {
    expect(adm('').Component).toBe(G.GdAdminEstructura);
    expect(adm('/').Component).toBe(G.GdAdminEstructura);
  });

  it('match estático admin (sin prefijo /admin/ — ya está en la URL)', () => {
    expect(adm('/usuarios').Component).toBe(G.GdAdminUsuarios);
    expect(adm('/estructura').Component).toBe(G.GdAdminEstructura);
    expect(adm('/catalogos').Component).toBe(G.GdAdminCatalogos);
    expect(adm('/parametros').Component).toBe(G.GdAdminParametros);
    expect(adm('/perifericos').Component).toBe(G.GdAdminPerifericos);
    expect(adm('/calendario').Component).toBe(G.GdCalendario);
    expect(adm('/notificaciones').Component).toBe(G.GdPlantillasNotif);
    expect(adm('/logs').Component).toBe(G.GdRetencionLogs);
    expect(adm('/backup').Component).toBe(G.GdBackup);
    expect(adm('/integraciones').Component).toBe(G.GdIntegraciones);
    expect(adm('/salud').Component).toBe(G.GdSaludSistema);
    expect(adm('/impresion').Component).toBe(G.GdImpresion);
    expect(adm('/digitalizacion').Component).toBe(G.GdDigitalizacion);
  });

  it('fallback admin → Estructura para path desconocido', () => {
    expect(adm('/nope').Component).toBe(G.GdAdminEstructura);
  });

  it('routes op NO se resuelven en mode=admin (aislamiento)', () => {
    // `/buzon` solo existe en OP. En admin → fallback (Estructura).
    expect(adm('/buzon').Component).toBe(G.GdAdminEstructura);
  });
});

describe('resolveGdRoute — exports internos', () => {
  it('expone OP_STATIC + ADMIN_STATIC + OP_DYNAMIC + ADMIN_DYNAMIC', () => {
    expect(_internal.OP_STATIC).toBeTypeOf('object');
    expect(_internal.ADMIN_STATIC).toBeTypeOf('object');
    expect(Array.isArray(_internal.OP_DYNAMIC)).toBe(true);
    expect(Array.isArray(_internal.ADMIN_DYNAMIC)).toBe(true);
  });

  it('OP_STATIC cubre todos los sub-módulos operativos', () => {
    const keys = Object.keys(_internal.OP_STATIC);
    expect(keys.length).toBeGreaterThan(25);
    expect(keys.some((k) => k.startsWith('/ventanilla'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/buzon'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/pqrsd'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/correspondencia'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/documentos') || k.startsWith('/plantillas'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/firmas'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/trd') || k.startsWith('/tvd'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/expedientes'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/auditoria') || k.startsWith('/reportes'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/ia'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/comunicaciones'))).toBe(true);
  });

  it('ADMIN_STATIC tiene los items principales del admin del módulo', () => {
    const keys = Object.keys(_internal.ADMIN_STATIC);
    expect(keys).toContain('/usuarios');
    expect(keys).toContain('/estructura');
    expect(keys).toContain('/catalogos');
    expect(keys).toContain('/parametros');
    expect(keys).toContain('/perifericos');
  });
});
