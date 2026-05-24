/**
 * SugerenciaClasificacion — GD-UI-0072. Inline / embebida.
 *
 * Sugiere serie + subserie + tipo documental + dependencia probable
 * basado en el contenido del documento. El usuario puede aceptar,
 * rechazar o aceptar parcial — todo queda en feedback de entrenamiento.
 *
 * IA-001 read. Diseñado para embeberse en CargarDocumentoModal,
 * ExpedienteFicha, RadicadoFicha, etc.
 */
import React, { useState } from 'react';

import {
  useSugerirClasificacionIA, useFeedbackSugerenciaIA,
} from './useGdIA.js';

export function SugerenciaClasificacion({
  session,
  contenido,           // texto o id de documento
  documentoId,
  expedienteId,
  onAceptar,           // (sugerencia) => void
  compact = false,
}) {
  const sugerir = useSugerirClasificacionIA(session);
  const feedback = useFeedbackSugerenciaIA(session);
  const [resultado, setResultado] = useState(null);
  const [feedbackEnviado, setFeedbackEnviado] = useState(false);

  async function handleSugerir() {
    setFeedbackEnviado(false);
    try {
      const r = await sugerir.submit({
        contenido, documento_id: documentoId, expediente_id: expedienteId,
      });
      setResultado(r);
    } catch { /* hook captura */ }
  }

  async function handleAceptar() {
    if (!resultado) return;
    onAceptar?.(resultado);
    try {
      await feedback.submit(resultado.id, { decision: 'aceptada' });
      setFeedbackEnviado(true);
    } catch { /* */ }
  }

  async function handleRechazar(motivo) {
    if (!resultado) return;
    try {
      await feedback.submit(resultado.id, { decision: 'rechazada', motivo });
      setResultado(null);
      setFeedbackEnviado(true);
    } catch { /* */ }
  }

  return (
    <div data-testid="ia-sug-clas" className={compact ? '' : 'card'}
      style={compact ? {} : { padding: 'var(--s-4)' }}>
      {!resultado && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleSugerir}
            disabled={sugerir.submitting}
            data-testid="ia-sug-clas-pedir"
          >
            {sugerir.submitting ? 'Analizando…' : '✨ Sugerir clasificación'}
          </button>
          <span className="muted" style={{ fontSize: 12 }}>
            La IA propone serie/subserie/tipo/dependencia probables.
          </span>
        </div>
      )}

      {sugerir.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 8 }}>
          <div className="body">{sugerir.error.message || 'Error al consultar IA.'}</div>
        </div>
      )}

      {resultado && (
        <div data-testid="ia-sug-clas-resultado" style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 11 }}>
            Sugerencia IA · confianza{' '}
            <strong data-testid="ia-sug-conf">{fmtPct(resultado.confianza)}</strong>
            {resultado.modelo && <> · modelo <code>{resultado.modelo}</code></>}
          </div>
          <ul style={{ margin: '4px 0 0', padding: 0, listStyle: 'none' }}>
            {resultado.serie && (
              <li><strong>Serie:</strong> {resultado.serie_codigo} — {resultado.serie}</li>
            )}
            {resultado.subserie && (
              <li><strong>Subserie:</strong> {resultado.subserie}</li>
            )}
            {resultado.tipo_documental && (
              <li><strong>Tipo documental:</strong> {resultado.tipo_documental}</li>
            )}
            {resultado.dependencia && (
              <li><strong>Dependencia probable:</strong> {resultado.dependencia}</li>
            )}
          </ul>
          {(resultado.razones || []).length > 0 && (
            <details style={{ marginTop: 6 }}>
              <summary className="muted" style={{ fontSize: 12, cursor: 'pointer' }}>
                Ver razones
              </summary>
              <ul data-testid="ia-sug-razones" style={{ fontSize: 12, paddingLeft: 18 }}>
                {resultado.razones.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </details>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button type="button" className="btn btn-accent btn-sm"
              onClick={handleAceptar}
              disabled={feedbackEnviado}
              data-testid="ia-sug-aceptar"
            >Aceptar</button>
            <button type="button" className="btn btn-danger btn-sm"
              onClick={() => handleRechazar('imprecisa')}
              disabled={feedbackEnviado}
              data-testid="ia-sug-rechazar"
            >Rechazar</button>
          </div>
          {feedbackEnviado && (
            <p className="muted" style={{ fontSize: 11, marginTop: 4 }} data-testid="ia-sug-feedback-ok">
              Feedback registrado. Gracias por ayudar a mejorar el modelo.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function fmtPct(v) {
  if (v == null) return '—';
  if (v <= 1) return `${(v * 100).toFixed(0)}%`;
  return `${Math.round(v)}%`;
}

export default SugerenciaClasificacion;
