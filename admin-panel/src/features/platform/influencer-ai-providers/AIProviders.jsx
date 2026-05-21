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
  isModalityConfigured,
  modalityLabel,
  modelSuggestionsFor,
  providerLabel,
  validateModelByProvider,
} from './aiProvidersData.js';
import { TestProviderModal } from './TestProviderModal.jsx';
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
  const [testingRow, setTestingRow] = useState(null);  // row del modal "Probar"

  const startEdit = (row) => {
    setForm({
      modality: row.modality,
      provider: row.provider || 'unset',
      model: row.model || '',
      api_key: '',  // siempre vacío (write-only)
      reuse_from_modality: null,  // checkbox de reuse
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

  const openTest = (row) => {
    setTestingRow(row);
  };

  const closeTest = () => {
    setTestingRow(null);
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
                // El botón "Probar" se habilita solo cuando la fila tiene
                // provider + model + hint (la env var queda implícita; el
                // backend valida y devuelve un mensaje accionable si falta).
                const canTest = isModalityConfigured(row);
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
                          onClick={() => openTest(row)}
                          disabled={!canTest}
                          title={canTest
                            ? 'Probar el provider configurado'
                            : 'Configura provider, modelo y API key para habilitar'}
                        >
                          Probar
                        </Button>
                      </div>
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
        {form ? (() => {
          // Sugerencias del datalist para el modelo según el provider activo
          // en el form (puede haber cambiado vs el row).
          const modelSuggestions = modelSuggestionsFor(form.provider, editing);
          const datalistId = `models-${editing}`;

          // Candidatos para reusar key: otras modalidades con el MISMO provider
          // que ya tienen `hint` (key configurada). El listado se construye
          // desde el response de la API; el `secret_ref` opaco nunca se expone
          // al cliente, solo el `hint` (últimos 4 chars).
          const reuseCandidates = rows.filter((r) =>
            r.modality !== editing
            && r.provider === form.provider
            && r.provider !== 'unset'
            && r.hint
          );

          const reuseSelected = Boolean(form.reuse_from_modality);

          return (
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
              <FormField label="Provider">
                <select
                  name="provider_choice"
                  value={form.provider}
                  onChange={(e) => setForm((p) => ({
                    ...p,
                    provider: e.target.value,
                    // Cambiar provider invalida un reuse pre-seleccionado
                    // — el candidato podría no aplicar al nuevo provider.
                    reuse_from_modality: null,
                  }))}
                  aria-label="Provider"
                  autoComplete="off"
                >
                  <option value="unset">— sin configurar —</option>
                  {(PROVIDERS_BY_MODALITY[editing] || []).map((p) => (
                    <option key={p} value={p}>{providerLabel(p)}</option>
                  ))}
                </select>
              </FormField>

              <FormField
                label="Modelo"
                hint={
                  modelSuggestions.length
                    ? `Sugerencias para ${providerLabel(form.provider)}: ${modelSuggestions.join(', ')}. Puedes escribir uno custom.`
                    : 'Escribe el identificador exacto del modelo.'
                }
              >
                <input
                  type="text"
                  name="model_identifier"
                  value={form.model}
                  onChange={(e) => setForm((p) => ({ ...p, model: e.target.value }))}
                  placeholder={modelSuggestions[0] || 'e.g. grok-4.3'}
                  list={modelSuggestions.length ? datalistId : undefined}
                  autoComplete="off"
                  spellCheck={false}
                  data-1p-ignore="true"
                  data-lpignore="true"
                />
                {modelSuggestions.length ? (
                  <datalist id={datalistId}>
                    {modelSuggestions.map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                ) : null}
              </FormField>

              {reuseCandidates.length ? (
                <fieldset className={styles.reuseGroup}>
                  <legend className={styles.reuseLegend}>
                    Reusar API Key existente
                  </legend>
                  <p className={styles.reuseHelp}>
                    Esta key se usa también en otra modalidad con el mismo
                    provider. Reusarla evita rotar manualmente la misma key
                    en cada modalidad. La key NUNCA se muestra en claro.
                  </p>
                  {reuseCandidates.map((cand) => {
                    const inputId = `reuse-${editing}-${cand.modality}`;
                    return (
                      <label key={cand.modality} htmlFor={inputId} className={styles.reuseItem}>
                        <input
                          id={inputId}
                          type="checkbox"
                          name={`reuse_from_${cand.modality}`}
                          checked={form.reuse_from_modality === cand.modality}
                          onChange={(e) => setForm((p) => ({
                            ...p,
                            reuse_from_modality: e.target.checked ? cand.modality : null,
                            // Si marcaste reuse, limpiamos la API key tipeada
                            // — el backend ignoraría secret_value en presencia
                            // de reuse_from_modality, pero mejor no enviarla
                            // ni dejarla en el DOM.
                            api_key: e.target.checked ? '' : p.api_key,
                          }))}
                        />
                        <span className={styles.reuseLabel}>
                          Usar la key de <strong>{modalityLabel(cand.modality)}</strong>
                          {' '}
                          <span className={styles.hintMono}>••••{cand.hint}</span>
                        </span>
                      </label>
                    );
                  })}
                </fieldset>
              ) : null}

              <FormField
                label="API Key (write-only)"
                hint={
                  reuseSelected
                    ? 'Deshabilitado: estás reusando la key de otra modalidad.'
                    : 'La key actual nunca se muestra; deja vacío para no cambiarla.'
                }
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
                  placeholder={reuseSelected ? 'Reusando key existente' : 'Se sobrescribirá la actual'}
                  autoComplete="off"
                  spellCheck={false}
                  data-1p-ignore="true"
                  data-lpignore="true"
                  aria-label="API Key del provider"
                  disabled={reuseSelected}
                  style={{ fontFamily: 'var(--font-mono)' }}
                />
              </FormField>

              {error ? (
                <AlertBanner tone="warn">{error}</AlertBanner>
              ) : null}
            </form>
          );
        })() : null}
      </Modal>

      <TestProviderModal
        open={Boolean(testingRow)}
        row={testingRow}
        onClose={closeTest}
        onTestProvider={onTestProvider}
      />
    </div>
  );
}
