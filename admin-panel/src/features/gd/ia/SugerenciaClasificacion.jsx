/**
 * SugerenciaClasificacion — GD-UI-0072.
 *
 * Componente embebible que llama a IA-001 para sugerir TRD +
 * tipo documental + dependencia probable. Render compacto con
 * confianza, justificación y CTAs aceptar/rechazar.
 *
 * Uso típico:
 *   <SugerenciaClasificacion
 *     session={session} roles={roles}
 *     entidad="documento" entidadId={docId}
 *     contexto={{ contenido, asunto, anexos }}
 *     onAplicar={(decision) => refrescarFicha()}
 *   />
 *
 * Si IA-001 está deshabilitado para el rol, el render es vacío
 * (no estorba el flujo principal).
 */
import React, { useState } from 'react';

import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useSugerenciaClasificacion, useAplicarSugerencia,
} from './useGdIa.js';

export function SugerenciaClasificacion({
  session, roles = [], entidad, entidadId, contexto = {},
  onAplicar,
}) {
  const tienePermiso = gdCanAny(roles, 'IA-001', 'RW');
  const sug = useSugerenciaClasificacion(session);
  const apl = useAplicarSugerencia(session);
  const [feedback, setFeedback] = useState(null);

  if (!tienePermiso) return null;

  async function pedirSugerencia() {
    setFeedback(null);
    try {
      await sug.submit({ ...contexto, entidad, entidad_id: entidadId });
    } catch (_) { /* error ya en hook */ }
  }

  async function aplicar(decision, ajustes) {
    setFeedback(null);
    try {
      const r = await apl.submit({
        entidad, entidad_id: entidadId, decision, ajustes,
      });
      setFeedback({ ok: true, decision, auditId: r?.audit_id });
      onAplicar?.(decision, r);
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  return (
    <div className="card" data-testid="ia-sug-clasif"
      style={{ padding: 'var(--s-4)', marginTop: 'var(--s-4)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between',
        alignItems: 'baseline', marginBottom: 'var(--s-2)' }}
      >
        <h3 style={{ fontSize: 14, margin: 0 }}>
          🤖 Sugerencia IA de clasificación
        </h3>
        <button type="button" className="btn btn-secondary btn-sm"
          onClick={pedirSugerencia}
          disabled={sug.loading}
          data-testid="ia-sug-clasif-pedir"
        >{sug.loading ? 'Pensando…' : 'Pedir sugerencia'}</button>
      </div>

      {sug.error && (
        <div className="alert danger" role="alert"
          data-testid="ia-sug-clasif-error"
        >
          <div className="body">
            {sug.error.code === 'ia_budget_exceeded'
              ? 'Presupuesto IA agotado para tu usuario / dependencia.'
              : (sug.error.message || 'Error consultando IA.')}
          </div>
        </div>
      )}

      {sug.data && (
        <div data-testid="ia-sug-clasif-resultado">
          <dl style={{ display: 'grid',
            gridTemplateColumns: 'max-content 1fr',
            gap: 'var(--s-1) var(--s-3)', margin: 'var(--s-2) 0' }}
          >
            <dt><strong>TRD sugerida</strong></dt>
            <dd>
              {sug.data.trd_sugerida?.serie ?? '—'}
              {sug.data.trd_sugerida?.subserie
                ? ` / ${sug.data.trd_sugerida.subserie}` : ''}
              {sug.data.trd_sugerida?.retencion != null && (
                <small style={{ color: 'var(--c-muted)' }}>
                  {' '}(retención: {sug.data.trd_sugerida.retencion} años)
                </small>
              )}
            </dd>
            <dt><strong>Tipo documental</strong></dt>
            <dd>{sug.data.tipo_documental ?? '—'}</dd>
            <dt><strong>Dependencia</strong></dt>
            <dd>{sug.data.dependencia?.nombre ?? '—'}</dd>
            <dt><strong>Confianza</strong></dt>
            <dd>
              <span className={`badge ${
                (sug.data.confianza ?? 0) >= 0.85 ? 'ok'
                  : (sug.data.confianza ?? 0) >= 0.6 ? 'warn' : 'danger'
              }`}
                data-testid="ia-sug-clasif-confianza"
              >
                {((sug.data.confianza ?? 0) * 100).toFixed(0)}%
              </span>
            </dd>
          </dl>
          {sug.data.justificacion && (
            <details style={{ marginTop: 'var(--s-2)' }}>
              <summary style={{ cursor: 'pointer', fontSize: 13 }}>
                Justificación
              </summary>
              <p style={{ fontSize: 13, color: 'var(--c-muted)',
                marginTop: 'var(--s-1)' }}
              >{sug.data.justificacion}</p>
            </details>
          )}
          <div style={{ display: 'flex', gap: 'var(--s-2)',
            marginTop: 'var(--s-3)' }}
          >
            <button type="button" className="btn btn-primary btn-sm"
              onClick={() => aplicar('aceptar')}
              disabled={apl.loading}
              data-testid="ia-sug-clasif-aceptar"
            >Aceptar sugerencia</button>
            <button type="button" className="btn btn-secondary btn-sm"
              onClick={() => aplicar('rechazar')}
              disabled={apl.loading}
              data-testid="ia-sug-clasif-rechazar"
            >Rechazar</button>
          </div>
        </div>
      )}

      {feedback && (
        <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
          role="status" style={{ marginTop: 'var(--s-3)' }}
          data-testid="ia-sug-clasif-feedback"
        >
          <div className="body">
            {feedback.ok
              ? (feedback.decision === 'aceptar'
                  ? `Sugerencia aceptada — registrado en auditoría (id: ${feedback.auditId || '?'}).`
                  : 'Sugerencia rechazada — feedback registrado.')
              : (feedback.error?.message || 'Error aplicando decisión.')}
          </div>
        </div>
      )}
    </div>
  );
}

export default SugerenciaClasificacion;
