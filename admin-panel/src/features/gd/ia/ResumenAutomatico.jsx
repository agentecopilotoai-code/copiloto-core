/**
 * ResumenAutomatico — GD-UI-0073. Resumen automático IA de un
 * documento o expediente.
 *
 * Embebible en ficha de documento / expediente. CTA "Generar
 * resumen" → muestra resumen + puntos clave + entidades
 * extraídas + metadata (modelo, tokens, coste).
 */
import React, { useState } from 'react';

import { gdCanAny } from '../../../permissions/gd-matrix.js';
import { useResumenDoc } from './useGdIa.js';

export function ResumenAutomatico({
  session, roles = [], entidad = 'documento', entidadId, defaultIdioma = 'es',
}) {
  const tienePermiso = gdCanAny(roles, 'IA-002', 'RW') ||
    gdCanAny(roles, 'IA-002', 'R');
  const puedeGenerar = gdCanAny(roles, 'IA-002', 'RW');
  const r = useResumenDoc(session);
  const [idioma, setIdioma] = useState(defaultIdioma);

  if (!tienePermiso) return null;

  async function generar() {
    try {
      await r.submit({ entidad, entidad_id: entidadId, idioma });
    } catch (_) { /* mostrado abajo */ }
  }

  return (
    <div className="card" data-testid="ia-resumen"
      style={{ padding: 'var(--s-4)', marginTop: 'var(--s-4)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'baseline', marginBottom: 'var(--s-2)', gap: 'var(--s-3)' }}
      >
        <h3 style={{ fontSize: 14, margin: 0 }}>📝 Resumen automático IA</h3>
        {puedeGenerar && (
          <div style={{ display: 'flex', gap: 'var(--s-2)' }}>
            <label style={{ fontSize: 12 }}>
              Idioma{' '}
              <select value={idioma} onChange={(e) => setIdioma(e.target.value)}
                data-testid="ia-resumen-idioma"
              >
                <option value="es">Español</option>
                <option value="en">English</option>
              </select>
            </label>
            <button type="button" className="btn btn-secondary btn-sm"
              onClick={generar} disabled={r.loading}
              data-testid="ia-resumen-generar"
            >{r.loading ? 'Generando…' : 'Generar resumen'}</button>
          </div>
        )}
      </div>

      {r.error && (
        <div className="alert danger" role="alert"
          data-testid="ia-resumen-error"
        >
          <div className="body">
            {r.error.code === 'ia_budget_exceeded'
              ? 'Presupuesto IA agotado.'
              : (r.error.message || 'Error generando resumen.')}
          </div>
        </div>
      )}

      {r.data && (
        <div data-testid="ia-resumen-contenido">
          <p style={{ marginTop: 'var(--s-2)' }}>{r.data.resumen}</p>
          {(r.data.puntos_clave || []).length > 0 && (
            <>
              <strong style={{ fontSize: 13 }}>Puntos clave</strong>
              <ul data-testid="ia-resumen-puntos">
                {r.data.puntos_clave.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
          {(r.data.entidades_extraidas || []).length > 0 && (
            <>
              <strong style={{ fontSize: 13 }}>Entidades detectadas</strong>
              <div data-testid="ia-resumen-entidades"
                style={{ display: 'flex', flexWrap: 'wrap',
                  gap: 'var(--s-1)', marginTop: 'var(--s-1)' }}
              >
                {r.data.entidades_extraidas.map((e, i) => (
                  <span key={i} className="badge">
                    {e.tipo}: {e.valor}
                  </span>
                ))}
              </div>
            </>
          )}
          <div style={{ fontSize: 11, color: 'var(--c-muted)',
            marginTop: 'var(--s-3)' }}
            data-testid="ia-resumen-meta"
          >
            modelo: <code>{r.data.modelo ?? '?'}</code> · tokens:{' '}
            {r.data.tokens ?? 0} · coste:{' '}
            ${(r.data.coste_usd ?? 0).toFixed(4)}
          </div>
        </div>
      )}

      {!r.data && !r.loading && !r.error && (
        <p className="muted" style={{ fontSize: 13 }}>
          Pulse "Generar resumen" para producir un resumen IA del{' '}
          {entidad === 'expediente' ? 'expediente' : 'documento'}.
        </p>
      )}
    </div>
  );
}

export default ResumenAutomatico;
