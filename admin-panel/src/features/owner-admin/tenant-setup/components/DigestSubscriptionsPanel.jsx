import { useEffect, useState } from 'react';

import {
  createDigestSubscription,
  deleteDigestSubscription,
  listDigestSubscriptions,
  updateDigestSubscription,
} from '../../../../services/coreApi.js';

const CADENCE_OPTIONS = [
  { value: 'daily', label: 'Diario (todos los días a las 08:00 del tenant)' },
  { value: 'weekly', label: 'Semanal (lunes 08:00)' },
];

function emptyForm() {
  return {
    recipient_email: '',
    recipient_whatsapp: '',
    cadence: 'daily',
    enabled: true,
  };
}

export default function DigestSubscriptionsPanel({ session, tenantId }) {
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
    } catch (err) {
      setError(err?.message || 'No se pudo actualizar la suscripción.');
    }
  }

  async function handleDelete(sub) {
    if (!window.confirm('¿Eliminar esta suscripción?')) return;
    setError('');
    try {
      await deleteDigestSubscription(session, tenantId, sub.id);
      await reload();
    } catch (err) {
      setError(err?.message || 'No se pudo eliminar la suscripción.');
    }
  }

  return (
    <fieldset
      className="wide"
      data-wizard-field="digest_subscriptions"
      style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}
    >
      <legend>Suscripciones a resúmenes (TASK-0067)</legend>
      <p className="hint" style={{ marginTop: 0 }}>
        Configura emails y WhatsApps del manager para recibir el resumen diario
        (08:00) o semanal (lunes 08:00). Reutiliza el SMTP de Alertas al equipo
        y la plantilla aprobada <code>digest_daily_v1</code> /{' '}
        <code>digest_weekly_v1</code> para WhatsApp.
      </p>

      {error ? (
        <p className="error" role="alert" style={{ color: 'var(--danger, #b00020)' }}>
          {error}
        </p>
      ) : null}

      <form className="form-grid" onSubmit={handleCreate} data-digest-form>
        <label className="wide">
          Email del destinatario
          <input
            type="email"
            placeholder="manager@empresa.com"
            value={form.recipient_email}
            onChange={(e) => setForm({ ...form, recipient_email: e.target.value })}
          />
        </label>
        <label className="wide">
          WhatsApp (E.164)
          <input
            type="text"
            placeholder="+573001234567"
            value={form.recipient_whatsapp}
            onChange={(e) => setForm({ ...form, recipient_whatsapp: e.target.value })}
          />
        </label>
        <label className="wide">
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
        <label className="inline-check wide">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          Activar al crear
        </label>
        <button type="submit" disabled={saving || !tenantId}>
          {saving ? 'Guardando…' : 'Agregar suscripción'}
        </button>
      </form>

      <hr style={{ margin: '1rem 0' }} />

      {loading ? <p>Cargando…</p> : null}
      {!loading && subscriptions.length === 0 ? (
        <p className="hint">Aún no hay suscripciones configuradas.</p>
      ) : null}

      {subscriptions.length > 0 ? (
        <table className="data-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Email</th>
              <th>WhatsApp</th>
              <th>Cadencia</th>
              <th>Estado</th>
              <th>Último envío</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {subscriptions.map((sub) => (
              <tr key={sub.id} data-digest-row={sub.id}>
                <td>{sub.recipient_email || '—'}</td>
                <td>{sub.recipient_whatsapp || '—'}</td>
                <td>{sub.cadence}</td>
                <td>
                  <label className="inline-check">
                    <input
                      type="checkbox"
                      checked={sub.enabled}
                      onChange={() => handleToggle(sub)}
                    />
                    {sub.enabled ? 'Activa' : 'Pausada'}
                  </label>
                </td>
                <td>{sub.last_sent_at ? new Date(sub.last_sent_at).toLocaleString() : 'Nunca'}</td>
                <td>
                  <button
                    type="button"
                    className="button-link"
                    onClick={() => handleDelete(sub)}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </fieldset>
  );
}
