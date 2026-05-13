import { useEffect, useMemo, useState } from 'react';

import {
  listMessengerChannels,
  upsertMessengerChannel,
} from '../../../services/coreApi.js';

const PROVIDER_OPTIONS = [
  {
    id: 'instagram_messenger',
    label: 'Instagram DM',
    recipientLabel: 'Instagram Business Account ID',
    helperUrl: 'https://developers.facebook.com/docs/messenger-platform/instagram',
  },
  {
    id: 'facebook_messenger',
    label: 'Facebook Messenger',
    recipientLabel: 'Facebook Page ID',
    helperUrl: 'https://developers.facebook.com/docs/messenger-platform',
  },
];

function emptyForm(provider) {
  return {
    provider,
    recipient_account_id: '',
    business_id: '',
    meta_access_token: '',
    app_secret: '',
    verify_token: '',
    account_mode: 'mock',
    service_window_hours: 24,
  };
}

function statusBadge(channel) {
  if (!channel) return 'sin configurar';
  if (channel.status !== 'active') return channel.status;
  return channel.account_mode === 'live' ? 'live' : 'mock';
}

export function SocialChannelsModule({ module: mod, session, tenant }) {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeProvider, setActiveProvider] = useState('instagram_messenger');
  const [form, setForm] = useState(() => emptyForm('instagram_messenger'));
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const tenantId = tenant?.id;

  useEffect(() => {
    if (!tenantId) return;
    setLoading(true);
    listMessengerChannels(session, tenantId)
      .then((data) => {
        setChannels(data?.channels || []);
        setError(null);
      })
      .catch((err) => setError(err?.message || 'No se pudieron cargar los canales sociales.'))
      .finally(() => setLoading(false));
  }, [session, tenantId]);

  useEffect(() => {
    setForm(emptyForm(activeProvider));
    setFeedback(null);
  }, [activeProvider]);

  const currentChannel = useMemo(
    () => channels.find((c) => c.provider === activeProvider) || null,
    [channels, activeProvider],
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!tenantId) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      const payload = {
        provider: activeProvider,
        recipient_account_id: form.recipient_account_id.trim(),
        business_id: form.business_id.trim() || null,
        meta_access_token: form.meta_access_token.trim() || undefined,
        app_secret: form.app_secret.trim() || undefined,
        verify_token: form.verify_token.trim() || undefined,
        account_mode: form.account_mode,
        service_window_hours: Number(form.service_window_hours) || 24,
      };
      const saved = await upsertMessengerChannel(session, tenantId, payload);
      setChannels((prev) => {
        const without = prev.filter((c) => c.provider !== activeProvider);
        return [...without, saved].sort((a, b) => a.provider.localeCompare(b.provider));
      });
      setFeedback({ kind: 'ok', text: 'Canal social actualizado.' });
      setForm(emptyForm(activeProvider));
    } catch (err) {
      setFeedback({ kind: 'error', text: err?.message || 'Error al guardar el canal.' });
    } finally {
      setSubmitting(false);
    }
  };

  const providerMeta = PROVIDER_OPTIONS.find((p) => p.id === activeProvider);

  return (
    <section className="module-card">
      <header>
        <h2>{mod?.label || 'Redes sociales'}</h2>
        <p className="hint">{mod?.summary}</p>
      </header>

      <div className="channel-tabs" role="tablist" aria-label="Proveedor de canal social">
        {PROVIDER_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={activeProvider === opt.id}
            className={activeProvider === opt.id ? 'tab-active' : ''}
            onClick={() => setActiveProvider(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="hint">Cargando canales…</p>}

      <div className="channel-summary">
        <h3>Estado actual</h3>
        {currentChannel ? (
          <ul className="kv-list">
            <li>
              <span>Estado</span>
              <strong>{statusBadge(currentChannel)}</strong>
            </li>
            <li>
              <span>{providerMeta?.recipientLabel}</span>
              <strong>
                {currentChannel.page_id || currentChannel.instagram_account_id || '—'}
              </strong>
            </li>
            <li>
              <span>Ventana de servicio</span>
              <strong>{currentChannel.service_window_hours}h</strong>
            </li>
            <li>
              <span>Token configurado</span>
              <strong>{currentChannel.token_configured ? 'sí' : 'no'}</strong>
            </li>
            <li>
              <span>App secret configurado</span>
              <strong>{currentChannel.app_secret_configured ? 'sí' : 'no'}</strong>
            </li>
            <li>
              <span>Verify token configurado</span>
              <strong>{currentChannel.verify_token_configured ? 'sí' : 'no'}</strong>
            </li>
          </ul>
        ) : (
          <p className="hint">Aún no se ha configurado este canal.</p>
        )}
      </div>

      <form className="messenger-channel-form" onSubmit={handleSubmit}>
        <h3>Configurar {providerMeta?.label}</h3>
        <p className="hint">
          La validación HMAC y la ventana 24h reusan la misma lógica del webhook WhatsApp.
        </p>

        <label>
          {providerMeta?.recipientLabel}
          <input
            type="text"
            required
            value={form.recipient_account_id}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, recipient_account_id: e.target.value }))
            }
          />
        </label>

        <label>
          Business ID (opcional)
          <input
            type="text"
            value={form.business_id}
            onChange={(e) => setForm((prev) => ({ ...prev, business_id: e.target.value }))}
          />
        </label>

        <label>
          Page access token
          <input
            type="password"
            value={form.meta_access_token}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, meta_access_token: e.target.value }))
            }
            placeholder="EAAG..."
          />
        </label>

        <label>
          App secret
          <input
            type="password"
            value={form.app_secret}
            onChange={(e) => setForm((prev) => ({ ...prev, app_secret: e.target.value }))}
          />
        </label>

        <label>
          Verify token (mínimo 16 caracteres)
          <input
            type="password"
            minLength={16}
            value={form.verify_token}
            onChange={(e) => setForm((prev) => ({ ...prev, verify_token: e.target.value }))}
          />
        </label>

        <label>
          Modo
          <select
            value={form.account_mode}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, account_mode: e.target.value }))
            }
          >
            <option value="mock">mock</option>
            <option value="live">live</option>
          </select>
        </label>

        <label>
          Ventana de servicio (horas)
          <input
            type="number"
            min={1}
            max={168}
            value={form.service_window_hours}
            onChange={(e) =>
              setForm((prev) => ({
                ...prev,
                service_window_hours: Number(e.target.value) || 24,
              }))
            }
          />
        </label>

        <button type="submit" disabled={submitting}>
          {submitting ? 'Guardando…' : 'Guardar canal'}
        </button>

        {feedback && (
          <p className={feedback.kind === 'ok' ? 'success' : 'error'}>{feedback.text}</p>
        )}
      </form>
    </section>
  );
}
