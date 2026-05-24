/**
 * NuevoRadicadoSalida — GD-UI-0008.
 *
 * Formulario más simple que el de entrada porque la salida típicamente
 * responde a un radicado de entrada existente. Validaciones clave:
 *  - El documento adjunto DEBE estar aprobado/firmado (validado por el
 *    backend; aquí solo filtramos en el picker).
 *  - El destinatario debe existir o crearse inline (reusa pattern del
 *    wizard de entrada — para no duplicar code aceptamos `tercero_id`).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useCrearRadicadoSalida } from './useGdRadicados.js';

export function NuevoRadicadoSalida({
  session,
  dependencias = [],
  onNavigate,
  onBuscarDocumento,
  onBuscarRadicadoRelacionado,
  ...shellProps
}) {
  const [form, setForm] = useState({
    radicado_relacionado_id: '',
    dependencia_origen_id: '',
    tercero_destinatario_id: '',
    asunto: '',
    documento_id: '',
  });
  const [docsDisponibles, setDocsDisponibles] = useState([]);
  const [busquedaDoc, setBusquedaDoc] = useState('');

  const { submitting, error, radicado, submit } = useCrearRadicadoSalida(session);

  function update(k, v) { setForm((p) => ({ ...p, [k]: v })); }

  async function buscarDocumento(q) {
    setBusquedaDoc(q);
    if (q.length < 2 || !onBuscarDocumento) {
      setDocsDisponibles([]);
      return;
    }
    try {
      const res = await onBuscarDocumento(q);
      const items = Array.isArray(res) ? res : (res?.items || []);
      // Solo aprobados/firmados.
      setDocsDisponibles(items.filter(
        (d) => d.estado === 'aprobado' || d.estado === 'firmado',
      ));
    } catch {
      setDocsDisponibles([]);
    }
  }

  const isValid = Boolean(
    form.dependencia_origen_id &&
    form.tercero_destinatario_id &&
    form.asunto.trim().length >= 2 &&
    form.documento_id,
  );

  async function handleSubmit() {
    try {
      const r = await submit(form);
      onNavigate?.(`/gd/ventanilla/radicados/${r.id}`);
    } catch {
      /* error queda en hook */
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: 'Nuevo radicado de salida' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Nuevo radicado de salida</h1>
          <p className="subtitle">
            Registra un radicado oficial dirigido a un tercero externo.
            El documento adjunto debe estar aprobado o firmado.
          </p>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--s-6)' }}>
        <h2 style={{ fontSize: 17, marginTop: 0 }}>Datos del radicado</h2>

        <div className="field" style={{ marginBottom: 'var(--s-3)' }}>
          <label htmlFor="dep-origen">Dependencia de origen <span className="req">*</span></label>
          <select
            id="dep-origen"
            className="select"
            value={form.dependencia_origen_id}
            onChange={(e) => update('dependencia_origen_id', e.target.value)}
            data-testid="dep-origen-select"
          >
            <option value="">Seleccione…</option>
            {dependencias.map((d) => (
              <option key={d.id} value={d.id}>{d.nombre}</option>
            ))}
          </select>
        </div>

        <div className="field" style={{ marginBottom: 'var(--s-3)' }}>
          <label htmlFor="dest">Destinatario (tercero externo) <span className="req">*</span></label>
          <input
            id="dest"
            className="input"
            placeholder="UUID del tercero destinatario"
            value={form.tercero_destinatario_id}
            onChange={(e) => update('tercero_destinatario_id', e.target.value)}
            data-testid="dest-input"
          />
          <span className="hint">
            En la siguiente entrega se reemplaza por un picker con búsqueda.
          </span>
        </div>

        <div className="field" style={{ marginBottom: 'var(--s-3)' }}>
          <label htmlFor="asunto-sal">Asunto <span className="req">*</span></label>
          <input
            id="asunto-sal"
            className="input"
            value={form.asunto}
            onChange={(e) => update('asunto', e.target.value)}
            maxLength={500}
            data-testid="asunto-salida"
          />
        </div>

        <div className="field" style={{ marginBottom: 'var(--s-3)' }}>
          <label>Radicado de entrada relacionado (opcional)</label>
          {onBuscarRadicadoRelacionado ? (
            <input
              className="input"
              placeholder="Buscar por número…"
              value={form.radicado_relacionado_id}
              onChange={(e) => update('radicado_relacionado_id', e.target.value)}
            />
          ) : (
            <input
              className="input"
              placeholder="UUID o número"
              value={form.radicado_relacionado_id}
              onChange={(e) => update('radicado_relacionado_id', e.target.value)}
            />
          )}
        </div>

        <div className="field" style={{ marginBottom: 'var(--s-3)' }}>
          <label>Documento adjunto (aprobado o firmado) <span className="req">*</span></label>
          <input
            type="search"
            className="input"
            placeholder="Buscar documento…"
            value={busquedaDoc}
            onChange={(e) => buscarDocumento(e.target.value)}
            data-testid="doc-search"
          />
          {docsDisponibles.length > 0 && (
            <ul
              data-testid="doc-results"
              style={{
                listStyle: 'none', padding: 0, marginTop: 6,
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--r-md)',
                maxHeight: 200, overflow: 'auto',
              }}
            >
              {docsDisponibles.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => update('documento_id', d.id)}
                    style={{
                      width: '100%', textAlign: 'left',
                      padding: 'var(--s-2) var(--s-3)', border: 0,
                      background: form.documento_id === d.id
                        ? 'var(--sky-50)' : 'transparent',
                      cursor: 'pointer',
                    }}
                  >
                    <strong>{d.titulo}</strong>{' '}
                    <span className="muted" style={{ fontSize: 12 }}>
                      · {d.estado}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {form.documento_id && (
            <span className="hint">
              Documento seleccionado: <code>{form.documento_id}</code>
            </span>
          )}
        </div>

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            <div className="body">
              <div className="title">No se pudo radicar la salida.</div>
              <div>{error.body?.detail?.message || error.message || 'Error desconocido.'}</div>
            </div>
          </div>
        )}

        {radicado && (
          <div className="alert success" role="status" style={{ marginTop: 16 }}>
            <div className="body">
              <div className="title">Salida radicada.</div>
              <div>
                Número: <strong>{radicado.numero_radicado}</strong>.
              </div>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-5)' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSubmit}
            disabled={!isValid || submitting}
            data-testid="salida-submit"
          >
            {submitting ? 'Radicando…' : 'Radicar salida'}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => onNavigate?.('/gd/ventanilla')}
          >
            Cancelar
          </button>
        </div>
      </div>
    </GdShell>
  );
}

export default NuevoRadicadoSalida;
