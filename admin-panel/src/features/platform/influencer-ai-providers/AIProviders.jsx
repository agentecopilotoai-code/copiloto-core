/**
 * UI-INFLU-015 — Config de proveedores IA del módulo Influencer
 * (platform_owner only).
 */
import { useState } from 'react';

import { AlertBanner, Card, PageHeader, StatusBadge } from '../../../components/ui/index.js';
import {
  MODALITIES,
  PROVIDERS_BY_MODALITY,
  buildPatchPayload,
  modalityLabel,
  providerLabel,
  validateModelByProvider,
} from './aiProvidersData.js';


export function AIProviders({
  rows = [],
  health = {},
  onSave,
  onTestProvider,
}) {
  const [editing, setEditing] = useState(null);  // modality o null
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [testResults, setTestResults] = useState({});

  const startEdit = (row) => {
    setForm({
      modality: row.modality,
      provider: row.provider || 'unset',
      model: row.model || '',
      api_key: '',  // siempre vacío (write-only)
      params: row.params || {},
    });
    setEditing(row.modality);
  };

  const handleSave = async () => {
    const v = validateModelByProvider(form.provider, form.model);
    if (!v.valid) { setError(v.error); return; }
    setError(null);
    await onSave?.(form.modality, buildPatchPayload(form));
    setEditing(null);
  };

  const handleTest = async (row) => {
    const result = await onTestProvider?.(row.modality);
    setTestResults((prev) => ({ ...prev, [row.modality]: result }));
  };

  return (
    <div data-feature="platform-influencer-ai-providers">
      <PageHeader
        eyebrow="Platform Owner"
        title="Proveedores IA · módulo Influencer"
        description="Config exclusiva de la plataforma — los tenants nunca ven estos modelos."
      />

      <Card padding="md">
        <table aria-label="Proveedores AI" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th scope="col" align="left">Modalidad</th>
              <th scope="col" align="left">Provider</th>
              <th scope="col" align="left">Modelo</th>
              <th scope="col" align="left">Hint</th>
              <th scope="col" align="left">Health</th>
              <th scope="col" align="left">Última rotación</th>
              <th scope="col" align="left">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {MODALITIES.map((m) => {
              const row = rows.find((r) => r.modality === m.value) || { modality: m.value, provider: 'unset' };
              const healthState = health[m.value];
              const test = testResults[m.value];
              return (
                <tr key={m.value} style={{ borderTop: '1px solid var(--color-border-subtle, #e5e7eb)' }}>
                  <td>{modalityLabel(m.value)}</td>
                  <td>{providerLabel(row.provider)}</td>
                  <td>{row.model || '—'}</td>
                  <td>{row.hint ? `••••${row.hint}` : '—'}</td>
                  <td>
                    <StatusBadge tone={healthState === 'healthy' ? 'success' : healthState === 'degraded' ? 'warning' : 'neutral'}>
                      {healthState || 'unknown'}
                    </StatusBadge>
                  </td>
                  <td style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>
                    {row.rotated_at || '—'}
                  </td>
                  <td>
                    <button type="button" onClick={() => startEdit(row)}>Editar</button>
                    <button type="button" onClick={() => handleTest(row)} style={{ marginLeft: 4 }}>
                      Probar
                    </button>
                    {test && (
                      <div style={{ fontSize: 11, marginTop: 2 }}>
                        {test.ok ? `OK · ${test.elapsed_ms}ms` : `FAIL · ${test.error}`}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {editing && form && (
        <aside aria-label="Editar provider" style={{
          position: 'fixed', top: 0, right: 0, height: '100vh', width: 360,
          background: 'var(--color-surface, #fff)',
          borderLeft: '1px solid var(--color-border, #d1d5db)',
          padding: 'var(--space-3)',
          overflowY: 'auto',
          zIndex: 100,
        }}>
          <button type="button" onClick={() => setEditing(null)} aria-label="Cerrar" style={{ float: 'right' }}>×</button>
          <h2>Editar {modalityLabel(editing)}</h2>

          <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
            <span style={{ fontWeight: 600 }}>Provider</span>
            <select
              value={form.provider}
              onChange={(e) => setForm((p) => ({ ...p, provider: e.target.value }))}
              aria-label="Provider"
              style={{ width: '100%' }}
            >
              <option value="unset">— sin configurar —</option>
              {(PROVIDERS_BY_MODALITY[editing] || []).map((p) => (
                <option key={p} value={p}>{providerLabel(p)}</option>
              ))}
            </select>
          </label>

          <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
            <span style={{ fontWeight: 600 }}>Modelo</span>
            <input
              value={form.model}
              onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))}
              placeholder="e.g. grok-4.3"
              style={{ width: '100%' }}
            />
          </label>

          <label style={{ display: 'block', marginTop: 'var(--space-2)' }}>
            <span style={{ fontWeight: 600 }}>API Key (write-only)</span>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm((p) => ({ ...p, api_key: e.target.value }))}
              placeholder="Se sobrescribirá la actual"
              autoComplete="off"
              style={{ width: '100%' }}
            />
            <span style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>
              La key actual nunca se muestra; deja vacío para no cambiarla.
            </span>
          </label>

          {error && <AlertBanner tone="warn" style={{ marginTop: 'var(--space-2)' }}>{error}</AlertBanner>}

          <div style={{ marginTop: 'var(--space-3)', display: 'flex', gap: 4 }}>
            <button type="button" onClick={handleSave}>Guardar</button>
            <button type="button" onClick={() => setEditing(null)}>Cancelar</button>
          </div>
        </aside>
      )}
    </div>
  );
}
