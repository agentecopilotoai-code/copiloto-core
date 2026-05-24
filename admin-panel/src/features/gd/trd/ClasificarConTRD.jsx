/**
 * ClasificarConTRD — GD-UI-0048. Asocia un documento/expediente a una
 * serie + subserie + tipo documental de la TRD vigente.
 *
 * Puede usarse standalone (pasando `documentoId` o `expedienteId`)
 * o como modal embebido. Roles habilitados: TRD-READ + responsable
 * del documento.
 */
import React, { useMemo, useState } from 'react';

import { useTRD, useClasificarConTRD } from './useGdTRD.js';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';

export function ClasificarConTRD({
  session,
  documentoId,
  expedienteId,
  onSuccess,
  onCancel,
}) {
  const { items: series, loading, error } = useTRD(session);
  const [serieId, setSerieId] = useState('');
  const [subserieId, setSubserieId] = useState('');
  const [tipoId, setTipoId] = useState('');
  const [obs, setObs] = useState('');
  const [obsValid, setObsValid] = useState(false);
  const hook = useClasificarConTRD(session);

  const serie = useMemo(
    () => series.find((s) => s.id === serieId),
    [series, serieId],
  );
  const subserie = useMemo(
    () => (serie?.subseries || []).find((ss) => ss.id === subserieId),
    [serie, subserieId],
  );

  function pickSerie(id) {
    setSerieId(id);
    setSubserieId('');
    setTipoId('');
  }
  function pickSubserie(id) {
    setSubserieId(id);
    setTipoId('');
  }

  async function handle() {
    try {
      const payload = {
        serie_id: serieId, subserie_id: subserieId || null,
        tipo_documental_id: tipoId || null,
        observaciones: obs,
        documento_id: documentoId, expediente_id: expedienteId,
      };
      const r = await hook.submit(payload);
      onSuccess?.(r);
    } catch { /* hook */ }
  }

  const isValid = serieId && obsValid;

  return (
    <div data-testid="clasificar-form" className="card" style={{ padding: 'var(--s-5)' }}>
      <h2 style={{ marginTop: 0, fontSize: 16 }}>Clasificar con TRD</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Asigne la serie y, opcionalmente, la subserie y el tipo
        documental correspondientes a la TRD vigente.
      </p>

      {loading && <p className="muted">Cargando TRD…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'No se pudo cargar TRD.'}</div>
        </div>
      )}

      {!loading && !error && (
        <>
          <div className="field" style={{ marginTop: 'var(--s-3)' }}>
            <label>Serie <span className="req">*</span></label>
            <select
              className="select"
              value={serieId}
              onChange={(e) => pickSerie(e.target.value)}
              data-testid="clasificar-serie"
            >
              <option value="">— Seleccione —</option>
              {series.map((s) => (
                <option key={s.id} value={s.id}>{s.codigo} — {s.nombre}</option>
              ))}
            </select>
          </div>

          {serie && (serie.subseries || []).length > 0 && (
            <div className="field" style={{ marginTop: 'var(--s-3)' }}>
              <label>Subserie</label>
              <select
                className="select"
                value={subserieId}
                onChange={(e) => pickSubserie(e.target.value)}
                data-testid="clasificar-subserie"
              >
                <option value="">— Sin subserie —</option>
                {serie.subseries.map((ss) => (
                  <option key={ss.id} value={ss.id}>{ss.codigo} — {ss.nombre}</option>
                ))}
              </select>
            </div>
          )}

          {subserie && (subserie.tipos || []).length > 0 && (
            <div className="field" style={{ marginTop: 'var(--s-3)' }}>
              <label>Tipo documental</label>
              <select
                className="select"
                value={tipoId}
                onChange={(e) => setTipoId(e.target.value)}
                data-testid="clasificar-tipo"
              >
                <option value="">— Sin tipo específico —</option>
                {subserie.tipos.map((t) => (
                  <option key={t.id} value={t.id}>{t.nombre}</option>
                ))}
              </select>
            </div>
          )}

          <div style={{ marginTop: 'var(--s-3)' }}>
            <JustificacionRequiredField
              value={obs}
              onChange={(v, ok) => { setObs(v); setObsValid(ok); }}
              label="Observaciones / justificación"
              id="clasificar-obs"
            />
          </div>

          {hook.error && (
            <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
              <div className="body">{hook.error.message || 'No se pudo clasificar.'}</div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
            <button type="button" className="btn btn-ghost" onClick={onCancel}
              data-testid="clasificar-cancel"
            >Cancelar</button>
            <button type="button" className="btn btn-accent"
              disabled={!isValid || hook.submitting} onClick={handle}
              data-testid="clasificar-submit"
            >{hook.submitting ? 'Clasificando…' : 'Clasificar'}</button>
          </div>
        </>
      )}
    </div>
  );
}

export default ClasificarConTRD;
