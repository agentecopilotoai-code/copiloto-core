/**
 * DeteccionPII — GD-UI-0076. Detección de PII y alertas de
 * privacidad en contenido cargado (Ley 1581/2012 de Colombia).
 *
 * Componente embebible (al cargar adjunto) Y vista standalone
 * (revisión global por admin_seguridad). Detecta:
 *  - Cédula, NIT, pasaporte, teléfono
 *  - Email, dirección
 *  - Datos sensibles ley 1581 (salud, orientación, política,
 *    biometría, niños)
 *
 * Reporta hallazgos con severidad + valor REDACTADO (nunca el
 * valor crudo, defensa-en-profundidad).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useDeteccionPII, useFalsoPositivoPii,
} from './useGdIa.js';

const SEVERIDAD_TONE = {
  alta: 'danger',
  media: 'warn',
  baja: 'info',
};

/**
 * Variante embebida (sin GdShell). Recibe contenido o adjuntoId.
 * Render compacto con alertas al detectar.
 */
export function DeteccionPIIInline({
  session, roles = [], contenido, adjuntoId, sensible = false,
  onHallazgos,
}) {
  const tienePermiso = gdCanAny(roles, 'IA-005', 'RW');
  const d = useDeteccionPII(session);
  const fp = useFalsoPositivoPii(session);

  if (!tienePermiso) return null;

  async function escanear() {
    try {
      const r = await d.submit({
        contenido, adjunto_id: adjuntoId, sensible,
      });
      onHallazgos?.(r?.hallazgos || []);
    } catch (_) { /* mostrado */ }
  }

  async function reportarFp(hallazgo) {
    try {
      await fp.submit({
        hallazgo_id: hallazgo.id || `${hallazgo.tipo}-${hallazgo.span?.[0]}`,
        motivo: 'falso_positivo_usuario',
      });
    } catch (_) { /* swallow */ }
  }

  return (
    <div className="card" data-testid="ia-pii-inline"
      style={{ padding: 'var(--s-3)', marginTop: 'var(--s-3)' }}
    >
      <div style={{ display: 'flex',
        justifyContent: 'space-between', alignItems: 'baseline' }}
      >
        <strong style={{ fontSize: 13 }}>🛡️ Análisis de privacidad</strong>
        <button type="button" className="btn btn-secondary btn-sm"
          onClick={escanear} disabled={d.loading}
          data-testid="ia-pii-escanear"
        >{d.loading ? 'Escaneando…' : 'Escanear ahora'}</button>
      </div>

      {d.error && (
        <div className="alert danger" role="alert"
          data-testid="ia-pii-error"
        >
          <div className="body">
            {d.error.message || 'Error en análisis PII.'}
          </div>
        </div>
      )}

      {d.data && (
        <div data-testid="ia-pii-resultado" style={{ marginTop: 'var(--s-2)' }}>
          {!d.data.detectado ? (
            <div className="alert success" role="status"
              data-testid="ia-pii-limpio"
            >
              <div className="body">
                Sin hallazgos de información personal sensible.
              </div>
            </div>
          ) : (
            <>
              <div className="alert warn" role="alert"
                data-testid="ia-pii-aviso"
              >
                <div className="body">
                  Se detectaron {d.data.hallazgos.length} elemento(s)
                  con información personal. Considere redactar o
                  proteger el documento conforme a Ley 1581/2012.
                </div>
              </div>
              <ul style={{ listStyle: 'none', padding: 0,
                marginTop: 'var(--s-2)' }}
                data-testid="ia-pii-lista"
              >
                {d.data.hallazgos.map((h, i) => (
                  <li key={i}
                    style={{ padding: 'var(--s-2)',
                      borderLeft: `3px solid var(--c-${SEVERIDAD_TONE[h.severidad] || 'info'})`,
                      marginBottom: 'var(--s-1)' }}
                    data-testid="ia-pii-item"
                  >
                    <strong>{h.tipo}</strong>
                    {' '}
                    <span className={`badge ${SEVERIDAD_TONE[h.severidad] || 'info'}`}>
                      {h.severidad || 'media'}
                    </span>
                    {h.categoria_ley1581 && (
                      <small className="muted">
                        {' '}· {h.categoria_ley1581}
                      </small>
                    )}
                    {h.valor_redactado && (
                      <div style={{ fontSize: 12,
                        color: 'var(--c-muted)' }}
                      >
                        Valor: <code>{h.valor_redactado}</code>
                      </div>
                    )}
                    <button type="button"
                      className="btn btn-sm"
                      onClick={() => reportarFp(h)}
                      data-testid="ia-pii-fp"
                      style={{ marginTop: 'var(--s-1)' }}
                    >Reportar falso positivo</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Vista standalone para `gd.admin_seguridad`: revisión por lote
 * o ad-hoc de contenido pegado para análisis PII.
 */
export function DeteccionPII({
  session, roles = [], ...shellProps
}) {
  const [texto, setTexto] = useState('');
  const tienePermiso = gdCanAny(roles, 'IA-005', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Privacidad / PII' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Análisis de privacidad (PII)</h1>
          <p className="subtitle">
            Detecta información personal sensible en contenido
            arbitrario o adjuntos previo a cargarlo al sistema.
            Cumple Ley 1581/2012 de Colombia.
          </p>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="ia-pii-no-perm"
        >
          <div className="body">
            No tienes permiso para usar el análisis PII.
          </div>
        </div>
      )}

      {tienePermiso && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)',
            marginBottom: 'var(--s-3)' }}
          >
            <label htmlFor="ia-pii-texto" style={{ fontSize: 12 }}>
              Pega el texto a analizar
            </label>
            <textarea id="ia-pii-texto"
              value={texto} onChange={(e) => setTexto(e.target.value)}
              rows={6}
              placeholder="Ej. correo, formulario, transcripción de llamada…"
              style={{ width: '100%', marginTop: 'var(--s-1)' }}
              data-testid="ia-pii-textarea"
            />
          </div>

          {texto && (
            <DeteccionPIIInline
              session={session} roles={roles}
              contenido={texto}
            />
          )}
        </>
      )}
    </GdShell>
  );
}

export default DeteccionPII;
