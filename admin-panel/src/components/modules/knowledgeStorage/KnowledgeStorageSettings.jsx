import { useEffect, useState } from 'react';

import { getKnowledgeStorageSettings, updateKnowledgeStorageSettings } from '../../../services/coreApi.js';

const emptyForm = {
  backend: 'local',
  bucket: '',
  region: '',
  endpoint_url: '',
  prefix: '',
  access_key_id: '',
  secret_access_key: '',
};

function formFromConfig(config, tenantId) {
  return {
    backend: config?.backend || 'local',
    bucket: config?.bucket || '',
    region: config?.region || '',
    endpoint_url: config?.endpoint_url || '',
    prefix: config?.prefix || `tenants/${tenantId}/knowledge`,
    access_key_id: config?.access_key_id || '',
    secret_access_key: '',
  };
}

function hasValue(value) {
  return Boolean(String(value || '').trim());
}

export function KnowledgeStorageSettings({ module, session, tenant }) {
  const [form, setForm] = useState(emptyForm);
  const [config, setConfig] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const tenantId = tenant?.id;

  function updateField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function loadConfig() {
    if (!tenantId) return;
    setIsLoading(true);
    setNotice(null);
    getKnowledgeStorageSettings(session, tenantId)
      .then((response) => {
        setConfig(response);
        setForm(formFromConfig(response, tenantId));
      })
      .catch((error) => setNotice({ type: 'error', text: error.message }))
      .finally(() => setIsLoading(false));
  }

  useEffect(loadConfig, [session, tenantId]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!tenantId) return;
    setIsSaving(true);
    setNotice(null);
    const payload = {
      backend: form.backend,
      bucket: hasValue(form.bucket) ? form.bucket.trim() : null,
      region: hasValue(form.region) ? form.region.trim() : null,
      endpoint_url: hasValue(form.endpoint_url) ? form.endpoint_url.trim() : null,
      prefix: hasValue(form.prefix) ? form.prefix.trim() : `tenants/${tenantId}/knowledge`,
      access_key_id: hasValue(form.access_key_id) ? form.access_key_id.trim() : null,
    };
    if (hasValue(form.secret_access_key)) {
      payload.secret_access_key = form.secret_access_key;
    }

    try {
      const response = await updateKnowledgeStorageSettings(session, tenantId, payload);
      setConfig(response);
      setForm(formFromConfig(response, tenantId));
      setNotice({
        type: 'success',
        text: response.backend === 's3'
          ? 'S3 del tenant configurado. Las nuevas cargas de conocimiento usarán este bucket/prefix.'
          : 'Storage local activado para desarrollo.',
      });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="module-card wizard-card">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Storage por tenant</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label || 'Sin tenant seleccionado'}</strong>
        </div>
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}
      {isLoading ? <p className="notice info">Cargando configuración de storage…</p> : null}

      <div className="onboarding-layout">
        <form className="wizard-panel form-grid" onSubmit={handleSubmit}>
          <label>
            Backend
            <select onChange={(event) => updateField('backend', event.target.value)} value={form.backend}>
              <option value="local">Local develop/piloto</option>
              <option value="s3">S3 / MinIO por tenant</option>
            </select>
          </label>

          <label>
            Bucket S3 del tenant
            <input
              disabled={form.backend !== 's3'}
              onChange={(event) => updateField('bucket', event.target.value)}
              placeholder="copilotoia-tenant-acme-prod"
              required={form.backend === 's3'}
              value={form.bucket}
            />
          </label>

          <label>
            Región
            <input
              disabled={form.backend !== 's3'}
              onChange={(event) => updateField('region', event.target.value)}
              placeholder="us-east-1"
              value={form.region}
            />
          </label>

          <label>
            Endpoint S3 compatible
            <input
              disabled={form.backend !== 's3'}
              onChange={(event) => updateField('endpoint_url', event.target.value)}
              placeholder="https://s3.us-east-1.amazonaws.com"
              value={form.endpoint_url}
            />
            <small className="hint">
              Solo HTTPS y endpoints AWS / Cloudflare R2 / DigitalOcean Spaces.
              MinIO (HTTP) solo en entornos locales. Si configuras un endpoint
              propio debes proveer Access Key + Secret del tenant; nunca se
              usan credenciales de plataforma contra endpoints de tenant.
            </small>
          </label>

          <label className="wide">
            Prefix / carpeta lógica
            <input
              disabled={form.backend !== 's3'}
              onChange={(event) => updateField('prefix', event.target.value)}
              placeholder={`tenants/${tenantId}/knowledge`}
              value={form.prefix}
            />
          </label>

          <label>
            Access Key ID
            <input
              autoComplete="off"
              disabled={form.backend !== 's3'}
              onChange={(event) => updateField('access_key_id', event.target.value)}
              placeholder="AKIA… o usuario MinIO"
              value={form.access_key_id}
            />
          </label>

          <label>
            Secret Access Key
            <input
              autoComplete="new-password"
              disabled={form.backend !== 's3'}
              onChange={(event) => updateField('secret_access_key', event.target.value)}
              placeholder={config?.secret_configured ? 'Ya configurado; pegar solo para rotar' : 'Pegar secreto S3 del tenant'}
              type="password"
              value={form.secret_access_key}
            />
          </label>

          <div className="form-actions wide">
            <button className="secondary-action" disabled={isLoading} onClick={loadConfig} type="button">Refrescar</button>
            <button className="primary-action" disabled={isSaving || !tenantId} type="submit">
              {isSaving ? 'Guardando…' : 'Guardar storage'}
            </button>
          </div>
        </form>

        <aside className="wizard-panel">
          <h3>Estado</h3>
          <ul className="checklist">
            <li><strong>Backend</strong><small>{config?.backend || 'local'}</small></li>
            <li><strong>Bucket efectivo</strong><small>{config?.effective_bucket || 'Volumen local'}</small></li>
            <li><strong>Prefix</strong><small>{config?.prefix || `tenants/${tenantId}/knowledge`}</small></li>
            <li><strong>Secreto S3</strong><small>{config?.secret_configured ? 'Configurado en .secrets del tenant' : 'No configurado'}</small></li>
          </ul>
          <p className="hint">
            En desarrollo puedes usar local. En producción piloto selecciona S3 y usa un bucket único por tenant o un bucket compartido con prefix único y política IAM limitada.
          </p>
        </aside>
      </div>
    </section>
  );
}
