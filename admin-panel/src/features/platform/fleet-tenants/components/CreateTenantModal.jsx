/**
 * Modal "Crear tenant" — usado por el platform_owner desde Fleet.
 *
 * Llama `POST /v1/tenants` (NO `/v1/tenant-signup`). El platform_owner
 * NO queda como miembro del tenant nuevo. Tras crear:
 *   - Cierra el modal.
 *   - Refresca la tabla de Fleet.
 *   - NO redirige a `/t/{slug}/` — el user queda en Fleet. Si quiere
 *     operar el tenant, debe pasar por "Operar como tenant" (support_mode).
 */
import { useState } from 'react';

import { Modal, Button } from '../../../../components/ui/index.js';
import { createTenantAsPlatformOwner } from '../../../../services/coreApi.js';
import styles from '../FleetTenants.module.css';

const COUNTRY_OPTIONS = [
  { code: 'CO', label: 'Colombia' },
  { code: 'MX', label: 'México' },
  { code: 'AR', label: 'Argentina' },
  { code: 'CL', label: 'Chile' },
  { code: 'PE', label: 'Perú' },
  { code: 'EC', label: 'Ecuador' },
  { code: 'UY', label: 'Uruguay' },
];

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

export function CreateTenantModal({ session, open, onClose, onCreated }) {
  const [form, setForm] = useState({
    display_name: '',
    legal_name: '',
    slug: '',
    vertical_code: 'generic',
    country_code: 'CO',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!open) return null;

  const slugAuto = form.slug || slugify(form.display_name);
  const valid = form.display_name.trim().length >= 2 && slugAuto.length >= 2;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createTenantAsPlatformOwner(session, {
        slug: slugAuto,
        display_name: form.display_name.trim(),
        legal_name: form.legal_name.trim() || form.display_name.trim(),
        vertical_code: form.vertical_code.trim() || 'generic',
        country_code: form.country_code,
      });
      onCreated?.(created);
      onClose?.();
    } catch (err) {
      setError(err?.message || 'No se pudo crear el tenant');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Crear tenant nuevo"
      size="md"
    >
      <form onSubmit={handleSubmit} className={styles.createForm}>
        <p className={styles.helpText}>
          Como platform_owner creás el tenant para un cliente. <strong>Vos
          NO quedás como miembro del tenant</strong>. Para agregar usuarios,
          abrí el detalle del tenant y usá "Miembros".
        </p>

        <label className={styles.formField}>
          <span>Nombre del negocio *</span>
          <input
            type="text" required minLength={2} maxLength={200}
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            placeholder="Ej. Acme Spa"
            data-testid="create-tenant-display-name"
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
            type="text" minLength={2} maxLength={60}
            pattern="[a-z0-9-]+"
            value={form.slug}
            onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase() })}
            placeholder={`Auto: ${slugAuto}`}
            data-testid="create-tenant-slug"
          />
          <small>Solo minúsculas, números y guiones. URL será <code>/t/{slugAuto}/</code></small>
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
              {COUNTRY_OPTIONS.map((c) => (
                <option key={c.code} value={c.code}>{c.label}</option>
              ))}
            </select>
          </label>
        </div>

        {error ? (
          <div role="alert" className={styles.formError}>{error}</div>
        ) : null}

        <div className={styles.formActions}>
          <Button type="button" variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!valid || submitting}
            data-testid="create-tenant-submit"
          >
            {submitting ? 'Creando…' : 'Crear tenant'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
