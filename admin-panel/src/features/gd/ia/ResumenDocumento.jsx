/**
 * ResumenDocumento — GD-UI-0073. Resumen automático IA.
 *
 * Genera resumen ejecutivo + temas + entidades reconocidas para
 * un documento o expediente. Inline-embeddable. IA-002.
 */
import React, { useState } from 'react';

import { useGenerarResumenIA } from './useGdIA.js';

export function ResumenDocumento({
  session,
  documentoId,
  expedienteId,
  longitud = 'corto',  // corto | medio | extenso
  autoGenerar = false,
}) {
  const hook = useGenerarResumenIA(session);
  const [resultado, setResultado] = useState(null);
  const [len, setLen] = useState(longitud);

  async function generar(longitudOverride) {
    try {
      const r = await hook.submit({
        documento_id: documentoId,
        expediente_id: expedienteId,
        longitud: longitudOverride || len,
      });
      setResultado(r);
    } catch { /* hook captura */ }
  }

  React.useEffect(() => {
    if (autoGenerar && !resultado && !hook.submitting) {
      generar();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoGenerar]);

  return (
    <div className="card" style={{ padding: 'var(--s-4)' }} data-testid="ia-resumen">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <h3 style={{ fontSize: 14, margin: 0 }}>Resumen IA</h3>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <select className="select"
            style={{ width: 100, fontSize: 12 }}
            value={len}
            onChange={(e) => setLen(e.target.value)}
            data-testid="ia-resumen-len"
          >
            <option value="corto">Corto</option>
            <option value="medio">Medio</option>
            <option value="extenso">Extenso</option>
          </select>
          <button type="button" className="btn btn-secondary btn-sm"
            disabled={hook.submitting}
            onClick={() => generar()}
            data-testid="ia-resumen-pedir"
          >{hook.submitting ? 'Generando…' : (resultado ? 'Regenerar' : 'Generar')}</button>
        </div>
      </div>

      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 8 }}>
          <div className="body">{hook.error.message || 'Error al generar resumen.'}</div>
        </div>
      )}

      {resultado && (
        <div style={{ marginTop: 'var(--s-3)' }} data-testid="ia-resumen-resultado">
          <div className="muted" style={{ fontSize: 11 }}>
            Modelo: <code>{resultado.modelo || '—'}</code>
            {resultado.tokens && <> · {resultado.tokens} tokens</>}
            {' '}· generado el {fmt(resultado.generado_en)}
          </div>
          <p style={{ fontSize: 13, lineHeight: 1.55, marginTop: 6 }} data-testid="ia-resumen-texto">
            {resultado.resumen}
          </p>

          {(resultado.temas || []).length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="muted" style={{ fontSize: 11 }}>Temas principales</div>
              <div data-testid="ia-resumen-temas" style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {resultado.temas.map((t, i) => (
                  <span key={i} className="badge" style={{ fontSize: 11 }}>{t}</span>
                ))}
              </div>
            </div>
          )}

          {(resultado.entidades || []).length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div className="muted" style={{ fontSize: 11 }}>Entidades reconocidas</div>
              <ul data-testid="ia-resumen-entidades" style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                {resultado.entidades.map((e, i) => (
                  <li key={i}>
                    <strong>{e.texto}</strong>{' '}
                    <span className="muted">— {e.tipo}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {resultado.disclaimer && (
            <p className="muted" style={{ fontSize: 11, marginTop: 8, fontStyle: 'italic' }}>
              {resultado.disclaimer}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default ResumenDocumento;
