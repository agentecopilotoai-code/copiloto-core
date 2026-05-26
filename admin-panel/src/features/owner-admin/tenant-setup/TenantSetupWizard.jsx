/**
 * Tenant Setup — wizard mínimo del core.
 *
 * Solo expone configuración base del tenant: identidad institucional
 * (nombre, slug, país, vertical). Los tabs específicos de cada producto
 * se agregan cuando el producto se instala sobre el core.
 */
import { useState } from 'react';

import { PageHeader, Card, Button } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { createTenant } from '../../../services/coreApi.js';
import { COUNTRY_PROFILES, SUPPORTED_COUNTRIES } from './tenantSetupData.js';
import styles from './TenantSetupWizard.module.css';

function slugify(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
}

function NegocioTab({ tenant, onSaved, session, initialSignup, onTenantCreated }) {
  const [form, setForm] = useState({
    display_name: tenant?.display_name || '',
    legal_name: tenant?.legal_name || '',
    slug: tenant?.slug || '',
    vertical_code: tenant?.vertical_code || 'generic',
    country_code: tenant?.country_code || 'CO',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  const slugAuto = form.slug || slugify(form.display_name);
  const valid = form.display_name.trim().length >= 2 && slugAuto.length >= 2;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    setSaved(false);
    try {
      if (initialSignup) {
        const created = await createTenant(session, {
          slug: slugAuto,
          display_name: form.display_name.trim(),
          legal_name: form.legal_name.trim() || form.display_name.trim(),
          vertical_code: form.vertical_code.trim() || 'generic',
          country_code: form.country_code,
        });
        onTenantCreated?.(created);
      } else {
        onSaved?.(form);
      }
      setSaved(true);
    } catch (err) {
      setError(err?.message || 'No se pudo guardar el tenant.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card padding="lg">
      <form onSubmit={handleSubmit} className={styles.form}>
        <h3 className={styles.formHeading}>Datos del negocio</h3>
        <p className={styles.helpText}>
          Configuración base del tenant. La activación de módulos
          adicionales se hace desde el panel del platform_owner.
        </p>

        <label className={styles.formField}>
          <span>Nombre del negocio *</span>
          <input
            type="text" required minLength={2} maxLength={200}
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            data-testid="tenant-setup-display-name"
          />
        </label>

        <label className={styles.formField}>
          <span>Razón social</span>
          <input
            type="text" maxLength={200}
            value={form.legal_name}
            onChange={(e) => setForm({ ...form, legal_name: e.target.value })}
            placeholder="Por defecto: igual al nombre del negocio"
          />
        </label>

        <label className={styles.formField}>
          <span>Slug (URL del tenant)</span>
          <input
            type="text" minLength={2} maxLength={60} pattern="[a-z0-9-]+"
            value={form.slug}
            onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase() })}
            placeholder={`Auto: ${slugAuto}`}
            data-testid="tenant-setup-slug"
            disabled={!initialSignup && Boolean(tenant?.slug)}
          />
          <small>URL: <code>/t/{slugAuto}/</code></small>
        </label>

        <div className={styles.formRow}>
          <label className={styles.formField}>
            <span>Vertical *</span>
            <input
              type="text" required maxLength={64}
              value={form.vertical_code}
              onChange={(e) => setForm({ ...form, vertical_code: e.target.value })}
            />
          </label>
          <label className={styles.formField}>
            <span>País *</span>
            <select
              value={form.country_code}
              onChange={(e) => setForm({ ...form, country_code: e.target.value })}
            >
              {SUPPORTED_COUNTRIES.map((c) => (
                <option key={c} value={c}>{COUNTRY_PROFILES[c].label}</option>
              ))}
            </select>
          </label>
        </div>

        {error ? <div role="alert" className={styles.formError}>{error}</div> : null}
        {saved ? <div className={styles.formSuccess}>Cambios guardados.</div> : null}

        <div className={styles.formActions}>
          <Button type="submit" variant="primary"
            disabled={!valid || submitting}
            data-testid="tenant-setup-submit"
          >
            {submitting ? 'Guardando…' : initialSignup ? 'Crear tenant' : 'Guardar cambios'}
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function TenantSetupWizard({
  module: _module,
  session,
  tenant,
  initialSignup = false,
  onTenantCreated,
}) {
  void _module;
  const permissions = usePermissions();
  const targetTenant = tenant;

  const content = (
    <section className={styles.page}>
      <PageHeader
        eyebrow="Configuración"
        title={initialSignup ? 'Crear tu primer tenant' : 'Configuración del tenant'}
        description={
          initialSignup
            ? 'Completá los datos del negocio para activar tu cuenta.'
            : 'Datos generales del tenant.'
        }
      />
      <NegocioTab
        tenant={targetTenant}
        session={session}
        initialSignup={initialSignup}
        onTenantCreated={onTenantCreated}
      />
    </section>
  );

  if (initialSignup) return content;

  return (
    <RequirePermission permissions={permissions} capability={null} mode="R">
      {content}
    </RequirePermission>
  );
}

export default TenantSetupWizard;
