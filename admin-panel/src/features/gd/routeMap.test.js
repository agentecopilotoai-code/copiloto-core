import { describe, it, expect } from 'vitest';

import { resolveGdRoute, _internal } from './routeMap.js';
import * as G from './placeholders/index.jsx';

describe('resolveGdRoute', () => {
  it('landing → GdHome para cadena vacía', () => {
    const r = resolveGdRoute('');
    expect(r.Component).toBe(G.GdHome);
    expect(r.extraProps).toEqual({});
  });

  it('landing → GdHome para "/"', () => {
    const r = resolveGdRoute('/');
    expect(r.Component).toBe(G.GdHome);
  });

  it('match estático exacto', () => {
    expect(resolveGdRoute('/ventanilla').Component).toBe(G.GdVentanillaHome);
    expect(resolveGdRoute('/pqrsd').Component).toBe(G.GdPqrsdPanel);
    expect(resolveGdRoute('/documentos').Component).toBe(G.GdBiblioteca);
    expect(resolveGdRoute('/plantillas').Component).toBe(G.GdPlantillas);
    expect(resolveGdRoute('/trd').Component).toBe(G.GdTrdHome);
    expect(resolveGdRoute('/expedientes').Component).toBe(G.GdExpedientes);
    expect(resolveGdRoute('/auditoria').Component).toBe(G.GdAuditoria);
    expect(resolveGdRoute('/reportes').Component).toBe(G.GdReportes);
    expect(resolveGdRoute('/seguridad').Component).toBe(G.GdSeguridad);
    expect(resolveGdRoute('/admin/usuarios').Component).toBe(G.GdAdminUsuarios);
    expect(resolveGdRoute('/admin/perifericos').Component).toBe(G.GdAdminPerifericos);
    expect(resolveGdRoute('/ia/asistente').Component).toBe(G.GdAsistente);
    expect(resolveGdRoute('/comunicaciones/notificaciones').Component).toBe(G.GdNotificaciones);
  });

  it('match dinámico: ficha de documento con UUID', () => {
    const r = resolveGdRoute('/documentos/abc-123-uuid');
    expect(r.Component).toBe(G.GdDocumentoFicha);
    expect(r.extraProps).toEqual({ documentoId: 'abc-123-uuid' });
  });

  it('match dinámico: generar documento desde plantilla', () => {
    const r = resolveGdRoute('/plantillas/p1/generar');
    expect(r.Component).toBe(G.GdGenerarDocumento);
    expect(r.extraProps).toEqual({ plantillaId: 'p1' });
  });

  it('match dinámico: ficha PQRSD', () => {
    const r = resolveGdRoute('/pqrsd/p-2026-1');
    expect(r.Component).toBe(G.GdPqrsdFicha);
    expect(r.extraProps).toEqual({ pqrsdId: 'p-2026-1' });
  });

  it('match dinámico: ficha de expediente', () => {
    const r = resolveGdRoute('/expedientes/exp-001');
    expect(r.Component).toBe(G.GdExpedienteFicha);
    expect(r.extraProps).toEqual({ expedienteId: 'exp-001' });
  });

  it('match dinámico: tarea del buzón', () => {
    const r = resolveGdRoute('/buzon/tareas/t1');
    expect(r.Component).toBe(G.GdTareaFicha);
    expect(r.extraProps).toEqual({ tareaId: 't1' });
  });

  it('match dinámico: ficha radicado', () => {
    const r = resolveGdRoute('/ventanilla/radicados/r-2026-100');
    expect(r.Component).toBe(G.GdRadicadoFicha);
    expect(r.extraProps).toEqual({ radicadoId: 'r-2026-100' });
  });

  it('match dinámico: correspondencia ficha', () => {
    const r = resolveGdRoute('/correspondencia/c1');
    expect(r.Component).toBe(G.GdCorrespondenciaFicha);
    expect(r.extraProps).toEqual({ correspondenciaId: 'c1' });
  });

  it('match dinámico: evidencia de firma', () => {
    const r = resolveGdRoute('/firmas/evidencia/f1');
    expect(r.Component).toBe(G.GdEvidenciaFirma);
    expect(r.extraProps).toEqual({ firmaId: 'f1' });
  });

  it('match dinámico: evento de auditoría', () => {
    const r = resolveGdRoute('/auditoria/e1');
    expect(r.Component).toBe(G.GdAuditoriaEvento);
    expect(r.extraProps).toEqual({ eventoId: 'e1' });
  });

  it('match dinámico: clasificar con TRD (sin propId)', () => {
    const r = resolveGdRoute('/trd/clasificar');
    expect(r.Component).toBe(G.GdClasificarConTRD);
    expect(r.extraProps).toEqual({});
  });

  it('fallback → GdHome para path desconocido', () => {
    const r = resolveGdRoute('/nope/no/existe');
    expect(r.Component).toBe(G.GdHome);
  });

  it('fallback → GdHome para subPath undefined', () => {
    const r = resolveGdRoute(undefined);
    expect(r.Component).toBe(G.GdHome);
  });

  it('exporta tablas internas (smoke)', () => {
    expect(_internal.STATIC).toBeTypeOf('object');
    expect(Array.isArray(_internal.DYNAMIC)).toBe(true);
    expect(_internal.DYNAMIC.length).toBeGreaterThan(5);
  });

  it('STATIC tiene 30+ rutas cubriendo todos los sub-módulos', () => {
    // Cobertura cualitativa: cada subfeature del módulo debe tener al
    // menos una ruta estática.
    const keys = Object.keys(_internal.STATIC);
    expect(keys.length).toBeGreaterThan(30);
    // Cada subfeature representada
    expect(keys.some((k) => k.startsWith('/ventanilla'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/buzon'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/pqrsd'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/correspondencia'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/documentos') || k.startsWith('/plantillas'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/firmas'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/trd') || k.startsWith('/tvd'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/expedientes'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/admin'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/auditoria') || k.startsWith('/reportes'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/ia'))).toBe(true);
    expect(keys.some((k) => k.startsWith('/comunicaciones'))).toBe(true);
  });
});
