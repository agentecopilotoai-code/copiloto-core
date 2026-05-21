/**
 * UI-INFLU-015 — Config de proveedores IA del módulo Influencer
 * (platform_owner only).
 *
 * Modal de edición (no side-panel). El form usa nombres de campos opacos +
 * `autoComplete="off"` + `data-1p-ignore`/`data-lpignore` para evitar que
 * los password managers (1Password, LastPass, Chrome autofill) ofrezcan
 * credenciales del usuario en estos campos — esto NO es un login.
 */
import { useState } from 'react';

import {
  AlertBanner,
  Button,
  Card,
  FormField,
  Modal,
  PageHeader,
  StatusBadge,
} from '../../../components/ui/index.js';
import {
  MODALITIES,
  PROVIDERS_BY_MODALITY,
  buildPatchPayload,
  modalityLabel,
  providerLabel,
  validateModelByProvider,
} from './aiProvidersData.js';
import styles from './AIProviders.module.css';


export function AIProviders({
  rows = [],
  health = {},
  onSave,
  onTestProvider,
}) {
  const [editing, setEditing] = useState(null);  // modality o null
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testResults, setTestResults] = useState({});

  const startEdit = (row) => {
    setForm({
      modality: row.modality,
      provider: row.provider || 'unset',
      model: row.model || '',
      api_key: '',  // siempre vacío (write-only)
      params: row.params || {},
    });
    setError(null);
    setEditing(row.modality);
  };

  const closeModal = () => {
    if (saving) return;
    setEditing(null);
    setForm(null);
    setError(null);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const v = validateModelByProvider(form.provider, form.model);
    if (!v.valid) { setError(v.error); return; }
    setError(null);
    setSaving(true);
    try {
      await onSave?.(form.modality, buildPatchPayload(form));
      setEditing(null);
      setForm(null);
    } catch (err) {
      setError(err?.message || 'No se pudo guardar el cambio.');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (row) => {
    const result = await onTestProvider?.(row.modality);
    setTestResults((prev) => ({ ...prev, [row.modality]: result }));
  };

  // Nombres de campos opacos — no usan `email`/`password`/`username` para
  // que los browsers no autofilleen credenciales del usuario aquí.
  const formId = 'ai-providers-edit';

  return (
    <div data-feature="platform-influencer-ai-providers">
      <PageHeader
        eyebrow="Platform Owner"
        title="Proveedores IA · módulo Influencer"
        description="Config exclusiva de la plataforma — los tenants nunca ven estos modelos."
      />

      <Card padding="md">
        <div className={styles.tableWrap}>
          <table aria-label="Proveedores AI" className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Modalidad</th>
                <th scope="col">Provider</th>
                <th scope="col">Modelo</th>
                <th scope="col">Hint</th>
                <th scope="col">Health</th>
                <th scope="col">Última rotación</th>
                <th scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {MODALITIES.map((m) => {
                const row = rows.find((r) => r.modality === m.value) || {
                  modality: m.value, provider: 'unset',
                };
                const healthState = health[m.value];
                const test = testResults[m.value];
                return (
                  <tr key={m.value}>
                    <td className={styles.modalityCell}>{modalityLabel(m.value)}</td>
                    <td>{providerLabel(row.provider)}</td>
                    <td>{row.model || <span className={styles.muted}>—</span>}</td>
                    <td>
                      {row.hint ? (
                        <span className={styles.hintMono}>••••{row.hint}</span>
                      ) : (
                        <span className={styles.muted}>—</span>
                      )}
                    </td>
                    <td>
                      <StatusBadge
                        tone={
                          healthState === 'healthy' ? 'success'
                            : healthState === 'degraded' ? 'warning'
                            : 'neutral'
                        }
                      >
                        {healthState || 'unknown'}
                      </StatusBadge>
                    </td>
                    <td className={styles.rotatedAt}>{row.rotated_at || '—'}</td>
                    <td>
                      <div className={styles.actions}>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => startEdit(row)}
                        >
                          Editar
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => handleTest(row)}
                        >
                          Probar
                        </Button>
                      </div>
                      {test ? (
                        <div className={[
                          styles.testLine,
                          test.ok ? styles['testLine--ok'] : styles['testLine--fail'],
                        ].filter(Boolean).join(' ')}>
                          {test.ok ? `OK · ${test.elapsed_ms}ms` : `FAIL · ${test.error}`}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal
        open={Boolean(editing && form)}
        onClose={closeModal}
        title={editing ? `Editar ${modalityLabel(editing)}` : ''}
        description="Cambia el provider, modelo o rota la API key. La key actual nunca se muestra."
        size="sm"
        footer={
          <>
            <Button type="button" variant="ghost" onClick={closeModal} disabled={saving}>
              Cancelar
            </Button>
            <Button
              type="submit"
              form={formId}
              variant="primary"
              loading={saving}
              disabled={saving}
            >
              Guardar
            </Button>
          </>
        }
      >
        {form ? (
          <form
            id={formId}
            className={styles.form}
            onSubmit={handleSubmit}
            // `name` opaco + autoComplete off a nivel form para silenciar
            // password managers. No es un form de login.
            name="ai_provider_settings"
            autoComplete="off"
            spellCheck={false}
          >
            {/* Honeypot oculto: algunos managers buscan un par username/password
                en cualquier form. Si nuestros campos reales NO matchean, evitan
                la sugerencia. No renderizamos un honeypot real porque podría
                quedar tabbable; preferimos sólo nombres opacos + autoComplete off. */}
            <FormField label="Provider">
              <select
                name="provider_choice"
                value={form.provider}
                onChange={(e) => setForm((p) => ({ ...p, provider: e.target.value }))}
                aria-label="Provider"
                autoComplete="off"
              >
                <option value="unset">— sin configurar —</option>
                {(PROVIDERS_BY_MODALITY[editing] || []).map((p) => (
                  <option key={p} value={p}>{providerLabel(p)}</option>
                ))}
              </select>
            </FormField>

            <FormField label="Modelo" hint="Ej. grok-4.3, gpt-4o-mini, claude-sonnet-4-6">
              <input
                type="text"
                name="model_identifier"
                value={form.model}
                onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))}
                placeholder="e.g. grok-4.3"
                autoComplete="off"
                spellCheck={false}
                data-1p-ignore="true"
                data-lpignore="true"
              />
            </FormField>

            <FormField
              label="API Key (write-only)"
              hint="La key actual nunca se muestra; deja vacío para no cambiarla."
            >
              {/* type="text" intencional — type="password" dispara el flujo
                  de autofill de credenciales del navegador. Como no se trata
                  de una password personal del usuario sino de un token de
                  servicio, lo tratamos como un texto opaco. El backend
                  igualmente sólo persiste hint (últimos 4 chars). */}
              <input
                type="text"
                name="provider_token_rotation"
                value={form.api_key}
                onChange={(e) => setForm((p) => ({ ...p, api_key: e.target.value }))}
                placeholder="Se sobrescribirá la actual"
                autoComplete="off"
                spellCheck={false}
                data-1p-ignore="true"
                data-lpignore="true"
                aria-label="API Key del provider"
                style={{ fontFamily: 'var(--font-mono)' }}
              />
            </FormField>

            {error ? (
              <AlertBanner tone="warn">{error}</AlertBanner>
            ) : null}
          </form>
        ) : null}
      </Modal>
    </div>
  );
}
