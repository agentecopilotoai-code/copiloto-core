import { useEffect, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createDigestSubscription,
  deleteDigestSubscription,
  listDigestSubscriptions,
  updateDigestSubscription,
} from '../../../../services/coreApi.js';
import {
  CADENCE_OPTIONS,
  cadenceLabel,
  emptyForm,
  formatLastSent,
} from '../digestReportsData.js';
import styles from '../DigestReports.module.css';

/**
 * UI-008.4 — Suscripciones a resúmenes (TASK-0067).
 *
 * Relocated verbatim from `features/owner-admin/tenant-setup/components/` into
 * the Manager `digest-reports` feature. The component still self-manages its
 * subscriptions state and every `coreApi` call site, business rule (the "al
 * menos un email o whatsapp" validation, the cadence options, the enabled
 * toggle) and `data-*` attribute is preserved; UI-011 replaced the native
 * browser delete confirm with the global `useConfirm()` dialog.
 * The only changes from the legacy file: the `coreApi` import path for the new
 * location, and the legacy global classNames / inline styles swapped for the
 * feature CSS module with 100% `var(--...)` tokens.
 *
 * Still consumed as a default export by the tenant-setup wizard's
 * `NotificationsTab` from its new location.
 */
// BUG-104: `onMutation` opcional — el orchestrator lo pasa para que el
// summary header del DigestReports outer se refresque después de cada
// create/toggle/delete. El TenantSetupWizard sigue usando el panel sin
// la prop (preserva back-compat) — solo el orchestrator del feature lo
// pasa.
export default function DigestSubscriptionsPanel({ session, tenantId, onMutation }) {
  const confirm = useConfirm();
  const [subscriptions, setSubscriptions] = useState([]);
  const [form, setForm] = useState(emptyForm());
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  async function reload() {
    if (!tenantId) return;
    setLoading(true);
    setError('');
    try {
      const data = await listDigestSubscriptions(session, tenantId);
      setSubscriptions(Array.isArray(data?.subscriptions) ? data.subscriptions : []);
    } catch (err) {
      setError(err?.message || 'No se pudo cargar las suscripciones.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  async function handleCreate(event) {
    event.preventDefault();
    if (!tenantId) return;
    const email = (form.recipient_email || '').trim();
    const whatsapp = (form.recipient_whatsapp || '').trim();
    if (!email && !whatsapp) {
      setError('Indica al menos un email o un WhatsApp.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await createDigestSubscription(session, tenantId, {
        recipient_email: email || null,
        recipient_whatsapp: whatsapp || null,
        cadence: form.cadence,
        enabled: form.enabled,
      });
      setForm(emptyForm());
      await reload();
      // BUG-104: notificar al orchestrator para que refresque su summary.
      if (typeof onMutation === 'function') onMutation();
    } catch (err) {
      setError(err?.message || 'No se pudo crear la suscripción.');
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(sub) {
    setError('');
    try {
      await updateDigestSubscription(session, tenantId, sub.id, {
        enabled: !sub.enabled,
      });
      await reload();
      // BUG-104: notificar al orchestrator para que refresque su summary.
      if (typeof onMutation === 'function') onMutation();
    } catch (err) {
      setError(err?.message || 'No se pudo actualizar la suscripción.');
    }
  }

  async function handleDelete(sub) {
    const ok = await confirm({
      title: 'Eliminar suscripción',
      body: '¿Eliminar esta suscripción?',
      danger: true,
    });
    if (!ok) return;
    setError('');
    try {
      await deleteDigestSubscription(session, tenantId, sub.id);
      await reload();
      // BUG-104: notificar al orchestrator para que refresque su summary.
      if (typeof onMutation === 'function') onMutation();
    } catch (err) {
      setError(err?.message || 'No se pudo eliminar la suscripción.');
    }
  }

  return (
    <fieldset className={styles.panel} data-wizard-field="digest_subscriptions">
      <legend className={styles.panelLegend}>Suscripciones a resúmenes</legend>
      <p className={styles.hint}>
        Configurá emails y números de WhatsApp para recibir el resumen diario
        (08:00) o semanal (lunes 08:00) del rendimiento del negocio.
      </p>

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      <form className={styles.form} onSubmit={handleCreate} data-digest-form>
        <label className={styles.field}>
          Email del destinatario
          <input
            type="email"
            placeholder="manager@empresa.com"
            value={form.recipient_email}
            onChange={(e) => setForm({ ...form, recipient_email: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          WhatsApp (E.164)
          <input
            type="text"
            placeholder="+573001234567"
            value={form.recipient_whatsapp}
            onChange={(e) => setForm({ ...form, recipient_whatsapp: e.target.value })}
          />
        </label>
        <label className={styles.field}>
          Cadencia
          <select
            value={form.cadence}
            onChange={(e) => setForm({ ...form, cadence: e.target.value })}
          >
            {CADENCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.checkField}>
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          Activar al crear
        </label>
        <button type="submit" className={styles.submitButton} disabled={saving || !tenantId}>
          {saving ? 'Guardando…' : 'Suscribir destinatario'}
        </button>
      </form>

      <hr className={styles.divider} />

      {loading ? <p className={styles.hint}>Cargando…</p> : null}
      {!loading && subscriptions.length === 0 ? (
        <p className={styles.hint}>Aún no hay suscripciones configuradas.</p>
      ) : null}

      {subscriptions.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Email</th>
                <th>WhatsApp</th>
                <th>Cadencia</th>
                <th>Estado</th>
                <th>Último envío</th>
                <th aria-label="Acciones" />
              </tr>
            </thead>
            <tbody>
              {subscriptions.map((sub) => (
                <tr key={sub.id} data-digest-row={sub.id}>
                  <td>{sub.recipient_email || '—'}</td>
                  <td>{sub.recipient_whatsapp || '—'}</td>
                  <td>{cadenceLabel(sub.cadence)}</td>
                  <td>
                    <label className={styles.checkField}>
                      <input
                        type="checkbox"
                        checked={sub.enabled}
                        onChange={() => handleToggle(sub)}
                      />
                      {sub.enabled ? 'Activa' : 'Pausada'}
                    </label>
                  </td>
                  <td>{formatLastSent(sub.last_sent_at)}</td>
                  <td>
                    <button
                      type="button"
                      className={styles.linkButton}
                      onClick={() => handleDelete(sub)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </fieldset>
  );
}
