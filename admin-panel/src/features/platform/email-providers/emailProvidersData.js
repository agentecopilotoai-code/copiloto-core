/**
 * Helpers puros para la config de providers de email (v2.0.0).
 *
 * Espeja `aiProvidersData.js` pero para el subsistema de email. Sin
 * dependencias de React — el componente las importa para presentación
 * (selects, validación de campos).
 */

export const PROVIDER_TYPES = [
  { value: 'resend', label: 'Resend' },
  { value: 'sendgrid', label: 'SendGrid' },
  { value: 'mailgun', label: 'Mailgun' },
  { value: 'smtp', label: 'SMTP genérico' },
];

const PROVIDER_TYPE_LABELS = Object.fromEntries(
  PROVIDER_TYPES.map((p) => [p.value, p.label]),
);

export function providerTypeLabel(value) {
  return PROVIDER_TYPE_LABELS[value] || value || '—';
}

/**
 * Esquema esperado del `config_jsonb` por tipo de provider. La UI
 * muestra solo los campos relevantes para el tipo seleccionado.
 *
 * Resend / SendGrid: {} (solo necesitan api_key).
 * Mailgun: { domain: string, region: 'us' | 'eu' }.
 * SMTP: { host: string, port: number, username: string, use_tls: boolean }.
 */
export const CONFIG_SCHEMA_BY_PROVIDER_TYPE = {
  resend: [],
  sendgrid: [],
  mailgun: [
    { key: 'domain', label: 'Dominio Mailgun', type: 'text', placeholder: 'mg.copilotoia.com', required: true },
    { key: 'region', label: 'Región', type: 'select', options: ['us', 'eu'], required: true },
  ],
  smtp: [
    { key: 'host', label: 'Host SMTP', type: 'text', placeholder: 'smtp.gmail.com', required: true },
    { key: 'port', label: 'Puerto', type: 'number', placeholder: '587', required: true },
    { key: 'username', label: 'Usuario', type: 'text', placeholder: 'noreply@app.copilotoia.com', required: true },
    { key: 'use_tls', label: 'STARTTLS', type: 'checkbox' },
  ],
};

/**
 * Default `config_jsonb` para un tipo dado — útil al pre-llenar el form
 * en "create" cuando el operador cambia el `provider_type`.
 */
export function defaultConfigFor(providerType) {
  if (providerType === 'mailgun') return { domain: '', region: 'us' };
  if (providerType === 'smtp') {
    return { host: '', port: 587, username: '', use_tls: true };
  }
  return {};
}

/**
 * Valida que el config_jsonb tenga los campos requeridos por el tipo.
 * Devuelve `{ valid: boolean, error?: string }`.
 */
export function validateConfigFor(providerType, config) {
  const fields = CONFIG_SCHEMA_BY_PROVIDER_TYPE[providerType] || [];
  for (const f of fields) {
    if (!f.required) continue;
    const val = config?.[f.key];
    if (val === undefined || val === null || val === '') {
      return { valid: false, error: `Campo "${f.label}" es requerido` };
    }
  }
  return { valid: true };
}

/**
 * Convierte el form interno → body del POST/PATCH del backend.
 * Si `apiKey` está vacío, se omite del payload (caso PATCH sin rotación).
 */
export function buildCreatePayload(form) {
  return {
    code: form.code,
    provider_type: form.providerType,
    name: form.name,
    config_jsonb: form.config || {},
    api_key: form.apiKey,
    from_address_override: form.fromAddress || null,
    from_name_override: form.fromName || null,
    is_active: Boolean(form.isActive),
    priority: Number.isFinite(form.priority) ? form.priority : 100,
  };
}

export function buildUpdatePayload(form) {
  const payload = {
    code: form.code,
    provider_type: form.providerType,
    name: form.name,
    config_jsonb: form.config || {},
    from_address_override: form.fromAddress || null,
    from_name_override: form.fromName || null,
    is_active: Boolean(form.isActive),
    priority: Number.isFinite(form.priority) ? form.priority : 100,
  };
  if (form.apiKey) payload.api_key = form.apiKey;
  return payload;
}
