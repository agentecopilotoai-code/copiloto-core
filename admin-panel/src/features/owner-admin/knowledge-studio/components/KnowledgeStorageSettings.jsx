import { useEffect, useState } from 'react';

import {
  AlertBanner,
  Button,
  Card,
  CardHeader,
  FormField,
  PageHeader,
} from '../../../../components/ui/index.js';
import {
  getKnowledgeStorageSettings,
  updateKnowledgeStorageSettings,
} from '../../../../services/coreApi.js';
import styles from './KnowledgeStorageSettings.module.css';

/**
 * UI-022 — Knowledge Storage Settings (Owner / Admin · module `knowledge-storage`).
 *
 * Visual alignment to the design system. Replaces the legacy MVP layout
 * (`.module-card.wizard-card` + `.eyebrow` *"Storage por tenant"* + raw
 * `<button className="primary-action">` and `<label>field<input/></label>`
 * blocks) with the canonical primitives: `<PageHeader>`, `<Card>`/`<CardHeader>`,
 * `<FormField>`, `<Button>` and `<AlertBanner>` for notices.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/20 _ Config _ Tenant Setup
 * _ Voz del bot.html` (form patterns) + `docs/HTML DESIGN/Transversales/18 _ IA
 * _ Knowledge Studio.html` (Storage tile copy/tone). The editable form remains
 * a separate module from Knowledge Studio per the original split — the
 * read-only `<StorageSummary>` lives in Knowledge Studio (UI-016.2), while
 * THIS module owns the editable credentials/bucket form behind
 * `knowledge_storage.write` (RW). Capability gating is enforced by the router
 * via `moduleRegistry.js` — no in-component wrap required.
 *
 * Behaviour is preserved verbatim: same endpoints, same payload shape, same
 * validation rules. This refactor is visual-only.
 */
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

function noticeTone(type) {
  if (type === 'success') return 'success';
  if (type === 'error') return 'danger';
  return 'info';
}

function noticeTitle(type) {
  if (type === 'success') return 'Storage actualizado';
  if (type === 'error') return 'No se pudo guardar el storage';
  return 'Storage';
}

export function KnowledgeStorageSettings({ module, session, tenant }) {
  const [form, setForm] = useState(emptyForm);
  const [config, setConfig] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const tenantId = tenant?.id;
  const isS3 = form.backend === 's3';

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
        text:
          response.backend === 's3'
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
    <section className={styles.page}>
      <PageHeader
        eyebrow="IA & Canales"
        title={module?.label || 'Storage del Knowledge Studio'}
        description={
          module?.summary ||
          'Configura dónde se almacenan los documentos del bot. Compatible con S3 dedicado por tenant o storage local del entorno.'
        }
        actions={
          <div className={styles.tenantMeta}>
            <span>Tenant activo</span>
            <strong>{tenant?.label || 'Sin tenant seleccionado'}</strong>
          </div>
        }
      />

      {notice ? (
        <AlertBanner tone={noticeTone(notice.type)} title={noticeTitle(notice.type)}>
          {notice.text}
        </AlertBanner>
      ) : null}
      {isLoading ? (
        <AlertBanner tone="info" title="Cargando">
          Cargando configuración de storage…
        </AlertBanner>
      ) : null}

      <div className={styles.layout}>
        <Card padding="md">
          <CardHeader
            title="Configuración del backend"
            subtitle="Las credenciales se persisten en `.secrets/<tenant>` y nunca en la base de datos."
          />
          <form className={styles.formGrid} onSubmit={handleSubmit}>
            <FormField label="Backend">
              <select
                onChange={(event) => updateField('backend', event.target.value)}
                value={form.backend}
              >
                <option value="local">Local develop / piloto</option>
                <option value="s3">S3 / MinIO por tenant</option>
              </select>
            </FormField>

            <FormField label="Bucket S3 del tenant" required={isS3}>
              <input
                disabled={!isS3}
                onChange={(event) => updateField('bucket', event.target.value)}
                placeholder="copilotoia-tenant-acme-prod"
                value={form.bucket}
              />
            </FormField>

            <FormField label="Región">
              <input
                disabled={!isS3}
                onChange={(event) => updateField('region', event.target.value)}
                placeholder="us-east-1"
                value={form.region}
              />
            </FormField>

            <FormField
              label="Endpoint S3 compatible"
              hint="Solo URLs HTTPS de AWS S3, Cloudflare R2 o DigitalOcean Spaces. Si usás un servicio propio, completá Access Key y Secret de tu cuenta — las credenciales de la plataforma nunca se reutilizan."
            >
              <input
                disabled={!isS3}
                onChange={(event) => updateField('endpoint_url', event.target.value)}
                placeholder="https://s3.us-east-1.amazonaws.com"
                value={form.endpoint_url}
              />
            </FormField>

            <FormField label="Prefix / carpeta lógica" className={styles.wide}>
              <input
                disabled={!isS3}
                onChange={(event) => updateField('prefix', event.target.value)}
                placeholder={`tenants/${tenantId}/knowledge`}
                value={form.prefix}
              />
            </FormField>

            <FormField label="Access Key ID">
              <input
                autoComplete="off"
                disabled={!isS3}
                onChange={(event) => updateField('access_key_id', event.target.value)}
                placeholder="AKIA… o usuario MinIO"
                value={form.access_key_id}
              />
            </FormField>

            <FormField label="Secret Access Key">
              <input
                autoComplete="new-password"
                disabled={!isS3}
                onChange={(event) => updateField('secret_access_key', event.target.value)}
                placeholder={
                  config?.secret_configured
                    ? 'Ya configurado; pegar solo para rotar'
                    : 'Pegar secreto S3 del tenant'
                }
                type="password"
                value={form.secret_access_key}
              />
            </FormField>

            <div className={styles.actions}>
              <Button
                variant="secondary"
                disabled={isLoading}
                onClick={loadConfig}
                type="button"
              >
                Refrescar
              </Button>
              <Button
                variant="primary"
                disabled={isSaving || !tenantId}
                loading={isSaving}
                type="submit"
              >
                {isSaving ? 'Guardando…' : 'Guardar'}
              </Button>
            </div>
          </form>
        </Card>

        <Card padding="md" as="aside">
          <CardHeader
            title="Estado actual"
            subtitle="Configuración efectiva en el backend."
          />
          <ul className={styles.statusList}>
            <li className={styles.statusItem}>
              <strong>Backend</strong>
              <small>{config?.backend || 'local'}</small>
            </li>
            <li className={styles.statusItem}>
              <strong>Bucket efectivo</strong>
              <small>{config?.effective_bucket || 'Volumen local'}</small>
            </li>
            <li className={styles.statusItem}>
              <strong>Prefix</strong>
              <small>{config?.prefix || `tenants/${tenantId}/knowledge`}</small>
            </li>
            <li className={styles.statusItem}>
              <strong>Secreto S3</strong>
              <small>
                {config?.secret_configured
                  ? 'Configurado en .secrets del tenant'
                  : 'No configurado'}
              </small>
            </li>
          </ul>
          <p className={styles.sidebarHint}>
            En desarrollo puedes usar local. En producción piloto selecciona S3 y
            usa un bucket único por tenant o un bucket compartido con prefix
            único y política IAM limitada.
          </p>
        </Card>
      </div>
    </section>
  );
}
