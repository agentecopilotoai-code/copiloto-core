/**
 * Email Providers — v2.0.0. CRUD + test endpoint para
 * `app.email_providers`. Solo platform_owner. Espeja el patrón de
 * `AIProviders.jsx` (Card+table + Modal de edit + botón "Probar").
 *
 * Componente presentacional puro: recibe `rows`, `onCreate`, `onPatch`,
 * `onDelete`, `onTest` por props. El container conecta los handlers
 * al backend (`coreApi.js`).
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
  CONFIG_SCHEMA_BY_PROVIDER_TYPE,
  PROVIDER_TYPES,
  buildCreatePayload,
  buildUpdatePayload,
  defaultConfigFor,
  providerTypeLabel,
  validateConfigFor,
} from './emailProvidersData.js';
import styles from './EmailProviders.module.css';


const EMPTY_FORM = Object.freeze({
  id: null,
  code: '',
  providerType: 'resend',
  name: '',
  config: {},
  apiKey: '',
  fromAddress: '',
  fromName: '',
  isActive: true,
  priority: 100,
});


function rowToForm(row) {
  return {
    id: row.id,
    code: row.code || '',
    providerType: row.provider_type || 'resend',
    name: row.name || '',
    config: row.config_jsonb || {},
    apiKey: '',  // siempre vacío al editar (rotación opt-in)
    fromAddress: row.from_address_override || '',
    fromName: row.from_name_override || '',
    isActive: Boolean(row.is_active),
    priority: Number.isFinite(row.priority) ? row.priority : 100,
  };
}


export function EmailProviders({
  rows = [],
  onCreate,
  onPatch,
  onDelete,
  onTest,
}) {
  const [editing, setEditing] = useState(null); // 'create' | { id, ... } | null
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testingRow, setTestingRow] = useState(null);
  const [testToAddress, setTestToAddress] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const startCreate = () => {
    setForm({ ...EMPTY_FORM, config: defaultConfigFor(EMPTY_FORM.providerType) });
    setError(null);
    setEditing('create');
  };

  const startEdit = (row) => {
    setForm(rowToForm(row));
    setError(null);
    setEditing({ id: row.id });
  };

  const closeModal = () => {
    if (saving) return;
    setEditing(null);
    setForm(null);
    setError(null);
  };

  const handleProviderTypeChange = (newType) => {
    setForm((prev) => ({
      ...prev,
      providerType: newType,
      config: defaultConfigFor(newType),
    }));
  };

  const handleConfigChange = (key, value) => {
    setForm((prev) => ({ ...prev, config: { ...(prev.config || {}), [key]: value } }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form) return;
    if (!form.code || !form.name) {
      setError('Code y Name son requeridos');
      return;
    }
    if (editing === 'create' && !form.apiKey) {
      setError('API key es requerida al crear un provider');
      return;
    }
    const v = validateConfigFor(form.providerType, form.config);
    if (!v.valid) { setError(v.error); return; }
    setError(null);
    setSaving(true);
    try {
      if (editing === 'create') {
        await onCreate?.(buildCreatePayload(form));
      } else {
        await onPatch?.(form.id, buildUpdatePayload(form));
      }
      setEditing(null);
      setForm(null);
    } catch (err) {
      setError(err?.message || 'No se pudo guardar.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (row) => {
    if (!row?.id) return;
    // Hard delete — pedir confirmación explícita en native dialog.
    const ok = window.confirm?.(
      `¿Borrar el provider "${row.code}"? Esta acción no se puede deshacer.`
    );
    if (!ok) return;
    try {
      await onDelete?.(row.id);
    } catch (err) {
      // El container ya setea el AlertBanner de error.
    }
  };

  const openTest = (row) => {
    setTestingRow(row);
    setTestToAddress('');
    setTestResult(null);
  };

  const closeTest = () => {
    if (testing) return;
    setTestingRow(null);
    setTestToAddress('');
    setTestResult(null);
  };

  const runTest = async (event) => {
    event.preventDefault();
    if (!testingRow || !testToAddress) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await onTest?.(testingRow.id, { to_address: testToAddress });
      setTestResult(result || { ok: false, error: 'Sin respuesta del servidor' });
    } catch (err) {
      setTestResult({ ok: false, error: err?.message || 'Error desconocido' });
    } finally {
      setTesting(false);
    }
  };

  const configSchema = form
    ? (CONFIG_SCHEMA_BY_PROVIDER_TYPE[form.providerType] || [])
    : [];
  const formId = 'email-providers-edit';

  return (
    <div data-feature="platform-email-providers">
      <PageHeader
        eyebrow="Platform Owner"
        title="Proveedores de email"
        description="Configura uno o más providers (Resend, SendGrid, Mailgun, SMTP). El dispatcher recorre por prioridad ascendente y hace fallback al siguiente si el actual falla con un error retryable."
        actions={
          <Button variant="primary" onClick={startCreate}>
            Añadir provider
          </Button>
        }
      />

      <Card padding="md">
        <div className={styles.tableWrap}>
          <table aria-label="Email providers" className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Prioridad</th>
                <th scope="col">Code</th>
                <th scope="col">Tipo</th>
                <th scope="col">Nombre</th>
                <th scope="col">Sender</th>
                <th scope="col">Estado</th>
                <th scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className={styles.muted}>
                    Sin providers configurados. El sistema de email no enviará nada hasta agregar al menos uno.
                  </td>
                </tr>
              ) : null}
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.priority}</td>
                  <td className={styles.modalityCell}>{row.code}</td>
                  <td>{providerTypeLabel(row.provider_type)}</td>
                  <td>{row.name}</td>
                  <td>
                    {row.from_address_override ? (
                      <span className={styles.hintMono}>{row.from_address_override}</span>
                    ) : (
                      <span className={styles.muted}>— (default)</span>
                    )}
                  </td>
                  <td>
                    <StatusBadge tone={row.is_active ? 'success' : 'neutral'}>
                      {row.is_active ? 'activo' : 'inactivo'}
                    </StatusBadge>
                    {row.has_api_key ? null : (
                      <StatusBadge tone="warning">sin api key</StatusBadge>
                    )}
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <Button
                        type="button" size="sm" variant="ghost"
                        onClick={() => openTest(row)}
                        disabled={!row.has_api_key}
                        title={row.has_api_key ? 'Enviar email de prueba' : 'Rotá la API key primero'}
                      >
                        Probar
                      </Button>
                      <Button
                        type="button" size="sm" variant="secondary"
                        onClick={() => startEdit(row)}
                      >
                        Editar
                      </Button>
                      <Button
                        type="button" size="sm" variant="ghost"
                        onClick={() => handleDelete(row)}
                      >
                        Borrar
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal
        open={Boolean(editing && form)}
        onClose={closeModal}
        title={editing === 'create' ? 'Añadir provider de email' : 'Editar provider'}
        description="Code identifica al provider en logs (e.g. 'resend-main'). La API key se cifra antes de persistir y nunca se devuelve."
        size="md"
        footer={
          <>
            <Button type="button" variant="ghost" onClick={closeModal} disabled={saving}>
              Cancelar
            </Button>
            <Button type="submit" form={formId} variant="primary" loading={saving} disabled={saving}>
              Guardar
            </Button>
          </>
        }
      >
        {form ? (
          <form id={formId} className={styles.form} onSubmit={handleSubmit} autoComplete="off">
            <FormField label="Code (único, snake-case)">
              <input
                type="text" name="provider_code"
                value={form.code}
                onChange={(e) => setForm((p) => ({ ...p, code: e.target.value }))}
                placeholder="resend-main"
                autoComplete="off"
                disabled={editing !== 'create'}
              />
            </FormField>

            <FormField label="Nombre humano">
              <input
                type="text" name="provider_name"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="Resend principal"
                autoComplete="off"
              />
            </FormField>

            <FormField label="Tipo">
              <select
                name="provider_type_select"
                value={form.providerType}
                onChange={(e) => handleProviderTypeChange(e.target.value)}
                disabled={editing !== 'create'}
              >
                {PROVIDER_TYPES.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </FormField>

            {configSchema.length ? (
              <fieldset className={styles.form}>
                <legend>Configuración del provider</legend>
                {configSchema.map((f) => (
                  <FormField key={f.key} label={f.label}>
                    {f.type === 'select' ? (
                      <select
                        name={`cfg_${f.key}`}
                        value={form.config?.[f.key] ?? f.options?.[0]}
                        onChange={(e) => handleConfigChange(f.key, e.target.value)}
                      >
                        {(f.options || []).map((o) => (
                          <option key={o} value={o}>{o}</option>
                        ))}
                      </select>
                    ) : f.type === 'checkbox' ? (
                      <input
                        type="checkbox"
                        name={`cfg_${f.key}`}
                        checked={Boolean(form.config?.[f.key])}
                        onChange={(e) => handleConfigChange(f.key, e.target.checked)}
                      />
                    ) : (
                      <input
                        type={f.type}
                        name={`cfg_${f.key}`}
                        value={form.config?.[f.key] ?? ''}
                        onChange={(e) => handleConfigChange(
                          f.key,
                          f.type === 'number' ? Number(e.target.value) : e.target.value,
                        )}
                        placeholder={f.placeholder}
                        autoComplete="off"
                      />
                    )}
                  </FormField>
                ))}
              </fieldset>
            ) : null}

            <FormField
              label="API key"
              hint={
                editing === 'create'
                  ? 'Requerida. Se cifra antes de persistir.'
                  : 'Dejá vacío para no rotar. Si tipeás algo, reemplaza la actual.'
              }
            >
              <input
                type="text" name="provider_token_rotation"
                value={form.apiKey}
                onChange={(e) => setForm((p) => ({ ...p, apiKey: e.target.value }))}
                placeholder={editing === 'create' ? 'Pegá la API key del provider' : 'Dejá vacío para no rotar'}
                autoComplete="off"
                data-1p-ignore="true"
                data-lpignore="true"
                style={{ fontFamily: 'var(--font-mono)' }}
              />
            </FormField>

            <FormField label="From address (opcional)" hint="Override del sender global">
              <input
                type="email" name="from_address_override"
                value={form.fromAddress}
                onChange={(e) => setForm((p) => ({ ...p, fromAddress: e.target.value }))}
                placeholder="noreply@app.copilotoia.com"
                autoComplete="off"
              />
            </FormField>

            <FormField label="From name (opcional)">
              <input
                type="text" name="from_name_override"
                value={form.fromName}
                onChange={(e) => setForm((p) => ({ ...p, fromName: e.target.value }))}
                placeholder="CopilotoIA"
                autoComplete="off"
              />
            </FormField>

            <FormField label="Prioridad (orden ASC)" hint="Menor = se intenta primero. Convención: 10, 20, 30...">
              <input
                type="number" name="provider_priority"
                value={form.priority}
                onChange={(e) => setForm((p) => ({ ...p, priority: Number(e.target.value) }))}
                min={0} max={10000}
              />
            </FormField>

            <FormField label="Activo">
              <input
                type="checkbox" name="provider_is_active"
                checked={form.isActive}
                onChange={(e) => setForm((p) => ({ ...p, isActive: e.target.checked }))}
              />
            </FormField>

            {error ? (
              <AlertBanner tone="warning" title="Error">{error}</AlertBanner>
            ) : null}
          </form>
        ) : null}
      </Modal>

      <Modal
        open={Boolean(testingRow)}
        onClose={closeTest}
        title={testingRow ? `Probar provider: ${testingRow.code}` : ''}
        description="Envía un email real desde el provider seleccionado al destinatario indicado."
        size="sm"
        footer={
          <>
            <Button type="button" variant="ghost" onClick={closeTest} disabled={testing}>
              Cerrar
            </Button>
            <Button
              type="submit" form="email-provider-test"
              variant="primary" loading={testing} disabled={testing || !testToAddress}
            >
              Enviar prueba
            </Button>
          </>
        }
      >
        <form id="email-provider-test" onSubmit={runTest} className={styles.form}>
          <FormField label="Email destinatario">
            <input
              type="email" name="test_to_address"
              value={testToAddress}
              onChange={(e) => setTestToAddress(e.target.value)}
              placeholder="tu-email@example.com"
              autoComplete="off"
            />
          </FormField>
          {testResult ? (
            <AlertBanner tone={testResult.ok ? 'success' : 'warning'}
                         title={testResult.ok ? 'Enviado' : 'Falló'}>
              {testResult.ok ? (
                <>
                  Enviado vía {testResult.provider_code}.
                  {testResult.message_id ? ` Message ID: ${testResult.message_id}` : ''}
                  {' '}({Math.round(testResult.latency_ms || 0)} ms)
                </>
              ) : (
                <>
                  {testResult.error_class ? `${testResult.error_class}: ` : ''}
                  {testResult.error || 'Sin detalle'}
                </>
              )}
            </AlertBanner>
          ) : null}
        </form>
      </Modal>
    </div>
  );
}
