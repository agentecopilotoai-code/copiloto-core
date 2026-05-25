/**
 * ConfigModelosIA — GD-UI-0078. Configuración de modelos IA.
 *
 * Modelo + temperatura + max-tokens + guardrails. Admin sistema
 * (IA-007 RW). Cambios auditados con motivo.
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useConfigModelosIA, useActualizarConfigModelosIA,
} from './useGdIA.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const FUNCIONALIDADES = [
  { codigo: 'clasificacion', label: 'Sugerencia de clasificación' },
  { codigo: 'resumen', label: 'Resumen automático' },
  { codigo: 'busqueda_semantica', label: 'Búsqueda semántica' },
  { codigo: 'asistente', label: 'Asistente conversacional' },
  { codigo: 'pii', label: 'Detección de PII' },
];

export function ConfigModelosIA({ session, roles = [], ...shellProps }) {
  const { data, loading, error, refresh } = useConfigModelosIA(session);
  const editar = useActualizarConfigModelosIA(session);
  const [form, setForm] = useState({});
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const [info, setInfo] = useState(null);
  const puede = gdCanAny(roles, 'IA-007', 'RW');

  useEffect(() => {
    if (data) {
      const next = {};
      FUNCIONALIDADES.forEach(({ codigo }) => {
        next[codigo] = data[codigo] || {
          modelo: '', temperatura: 0.2, max_tokens: 2048, habilitado: true,
        };
      });
      next.guardrails = data.guardrails || {
        bloquear_pii_salida: true,
        bloquear_lenguaje_ofensivo: true,
        registrar_prompts: true,
      };
      next.limite_mensual_tokens = data.limite_mensual_tokens ?? 5000000;
      setForm(next);
    }
  }, [data]);

  function updateFunc(codigo, k, v) {
    setForm((p) => ({
      ...p,
      [codigo]: { ...(p[codigo] || {}), [k]: v },
    }));
  }
  function updateGuardrail(k, v) {
    setForm((p) => ({
      ...p,
      guardrails: { ...(p.guardrails || {}), [k]: v },
    }));
  }

  async function handle() {
    setInfo(null);
    try {
      // Mismo merge que el render: data como base, form sobre-escribe lo
      // editado. Sin esto, si el user guardara antes de que el effect
      // copiara data→form (raro pero posible), el payload sería {motivo}
      // sin las claves de funcionalidades/guardrails/límite.
      const payload = { motivo };
      FUNCIONALIDADES.forEach(({ codigo }) => {
        payload[codigo] = { ...(data[codigo] || {}), ...(form[codigo] || {}) };
      });
      payload.guardrails = { ...(data.guardrails || {}), ...(form.guardrails || {}) };
      payload.limite_mensual_tokens =
        form.limite_mensual_tokens ?? data.limite_mensual_tokens ?? null;
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
        { label: 'Configuración IA' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Configuración de modelos IA</h1>
          <p className="subtitle">
            Modelo + temperatura + guardrails por funcionalidad. Cambios
            auditados — requieren motivo.
          </p>
        </div>
      </div>

      {!puede && (
        <div className="alert warning" role="alert" data-testid="ia-cfg-no-perm">
          <div className="body">Solo administración del sistema puede configurar modelos.</div>
        </div>
      )}

      {puede && loading && <p className="muted">Cargando configuración…</p>}
      {puede && error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      {puede && data && (
        <>
          {/* Helpers de "merged view" — el form gana cuando el user editó,
              data llena los huecos en el primer render (antes de que el
              effect copie data→form). Evita race: la pestaña aparece con
              datos correctos sin esperar al efecto. */}
          {(() => null)()}
          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }} data-testid="ia-cfg-funcs">
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Por funcionalidad</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Funcionalidad</th>
                  <th>Modelo</th>
                  <th>Temperatura</th>
                  <th>Max tokens</th>
                  <th>Habilitada</th>
                </tr>
              </thead>
              <tbody>
                {FUNCIONALIDADES.map(({ codigo, label }) => {
                  const funcForm = form[codigo] || {};
                  const funcData = data[codigo] || {};
                  const modelo = funcForm.modelo ?? funcData.modelo ?? '';
                  const temperatura = funcForm.temperatura ?? funcData.temperatura ?? 0.2;
                  const maxTokens = funcForm.max_tokens ?? funcData.max_tokens ?? 2048;
                  const habilitadoVal = funcForm.habilitado ?? funcData.habilitado;
                  return (
                  <tr key={codigo} data-testid={`ia-cfg-func-${codigo}`}>
                    <td>{label}</td>
                    <td>
                      <input className="input" style={{ width: 160 }}
                        value={modelo}
                        onChange={(e) => updateFunc(codigo, 'modelo', e.target.value)}
                        placeholder="gpt-4o-mini"
                        data-testid={`ia-cfg-${codigo}-modelo`}
                      />
                    </td>
                    <td>
                      <input type="number" step={0.1} min={0} max={2} className="input" style={{ width: 80 }}
                        value={temperatura}
                        onChange={(e) => updateFunc(codigo, 'temperatura', Number(e.target.value))}
                        data-testid={`ia-cfg-${codigo}-temp`}
                      />
                    </td>
                    <td>
                      <input type="number" className="input" style={{ width: 100 }}
                        value={maxTokens}
                        onChange={(e) => updateFunc(codigo, 'max_tokens', Number(e.target.value))}
                        data-testid={`ia-cfg-${codigo}-max`}
                      />
                    </td>
                    <td>
                      <input type="checkbox"
                        checked={habilitadoVal !== false}
                        onChange={(e) => updateFunc(codigo, 'habilitado', e.target.checked)}
                        data-testid={`ia-cfg-${codigo}-hab`}
                      />
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }} data-testid="ia-cfg-guardrails">
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Guardrails de seguridad</h3>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
              <input type="checkbox"
                checked={(form.guardrails?.bloquear_pii_salida ?? data.guardrails?.bloquear_pii_salida) !== false}
                onChange={(e) => updateGuardrail('bloquear_pii_salida', e.target.checked)}
                data-testid="ia-cfg-gr-pii"
              />
              Bloquear PII en respuestas del asistente
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginTop: 8 }}>
              <input type="checkbox"
                checked={(form.guardrails?.bloquear_lenguaje_ofensivo ?? data.guardrails?.bloquear_lenguaje_ofensivo) !== false}
                onChange={(e) => updateGuardrail('bloquear_lenguaje_ofensivo', e.target.checked)}
                data-testid="ia-cfg-gr-ofensivo"
              />
              Bloquear lenguaje ofensivo / discriminatorio
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginTop: 8 }}>
              <input type="checkbox"
                checked={(form.guardrails?.registrar_prompts ?? data.guardrails?.registrar_prompts) !== false}
                onChange={(e) => updateGuardrail('registrar_prompts', e.target.checked)}
                data-testid="ia-cfg-gr-prompts"
              />
              Registrar prompts en auditoría (RNF-009)
            </label>
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginBottom: 'var(--s-4)' }} data-testid="ia-cfg-limite">
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Límite global</h3>
            <div className="field" style={{ maxWidth: 260 }}>
              <label>Límite mensual de tokens (entrada+salida)</label>
              <input type="number" className="input"
                value={form.limite_mensual_tokens ?? data.limite_mensual_tokens ?? ''}
                onChange={(e) => setForm({ ...form, limite_mensual_tokens: Number(e.target.value) })}
                data-testid="ia-cfg-limite-tokens"
              />
            </div>
          </div>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <JustificacionRequiredField
              value={motivo}
              onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
              label="Motivo del cambio"
              id="ia-cfg-motivo"
            />
            {info && (
              <div
                className={`alert ${info.ok ? 'success' : 'danger'}`}
                role="status"
                data-testid="ia-cfg-info"
                style={{ marginTop: 12 }}
              >
                <div className="body">
                  {info.ok ? 'Configuración actualizada.'
                    : `Error: ${info.error?.message || 'desconocido'}`}
                </div>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
              <button type="button" className="btn btn-accent"
                disabled={!motivoValid || editar.submitting} onClick={handle}
                data-testid="ia-cfg-guardar"
              >{editar.submitting ? 'Guardando…' : 'Guardar configuración'}</button>
            </div>
          </div>
        </>
      )}
    </GdShell>
  );
}

export default ConfigModelosIA;
