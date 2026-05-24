/**
 * RetencionLogs — GD-UI-0061. Política de retención de logs.
 *
 * Configura cuántos días se preservan los distintos tipos de log
 * (auditoría, acceso, errores, integración). Cambios auditados.
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  usePoliticaRetencionLogs,
  useActualizarPoliticaRetencionLogs,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TIPOS = [
  { key: 'retencion_auditoria_dias', label: 'Auditoría' },
  { key: 'retencion_acceso_dias', label: 'Acceso' },
  { key: 'retencion_errores_dias', label: 'Errores' },
  { key: 'retencion_integraciones_dias', label: 'Integraciones' },
];

export function RetencionLogs({ session, roles = [], ...shellProps }) {
  const { data, loading, error, refresh } = usePoliticaRetencionLogs(session);
  const editar = useActualizarPoliticaRetencionLogs(session);
  const [form, setForm] = useState({});
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const [info, setInfo] = useState(null);
  const puedeEditar = gdCanAny(roles, 'LOG-001', 'RW');

  useEffect(() => {
    if (data) {
      const next = {};
      TIPOS.forEach(({ key }) => { next[key] = data[key] ?? ''; });
      setForm(next);
    }
  }, [data]);

  async function handle() {
    setInfo(null);
    try {
      const payload = { motivo };
      for (const { key } of TIPOS) {
        payload[key] = form[key] === '' ? null : Number(form[key]);
      }
      await editar.submit(payload);
      setInfo({ ok: true });
      refresh();
    } catch (err) {
      setInfo({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Retención de logs' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Política de retención de logs</h1>
          <p className="subtitle">
            Días de preservación por tipo de bitácora. Aplica a la
            limpieza automática programada.
          </p>
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {data && (
        <div className="card" style={{ padding: 'var(--s-5)', maxWidth: 560 }} data-testid="log-card">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {TIPOS.map(({ key, label }) => (
              <div className="field" key={key}>
                <label>{label} (días)</label>
                <input
                  type="number" className="input"
                  value={form[key] ?? ''}
                  disabled={!puedeEditar}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                  data-testid={`log-${key}`}
                />
              </div>
            ))}
          </div>
          {puedeEditar && (
            <div style={{ marginTop: 'var(--s-4)' }}>
              <JustificacionRequiredField
                value={motivo}
                onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
                label="Motivo del cambio"
                id="log-motivo"
              />
            </div>
          )}
          {info && (
            <div
              className={`alert ${info.ok ? 'success' : 'danger'}`}
              role="status"
              style={{ marginTop: 12 }}
              data-testid="log-info"
            >
              <div className="body">
                {info.ok ? 'Política actualizada.'
                  : `Error: ${info.error?.message || 'desconocido'}`}
              </div>
            </div>
          )}
          {puedeEditar && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
              <button type="button" className="btn btn-accent"
                disabled={!motivoValid || editar.submitting} onClick={handle}
                data-testid="log-guardar"
              >{editar.submitting ? 'Guardando…' : 'Guardar política'}</button>
            </div>
          )}
        </div>
      )}
    </GdShell>
  );
}

export default RetencionLogs;
