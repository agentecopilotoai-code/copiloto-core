import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  listMessengerChannels,
  upsertMessengerChannel,
} from '../../../../services/coreApi.js';
import { buildPayload, channelForProvider, emptyForm } from '../socialChannelsData.js';

/**
 * Data layer for the Canales · Instagram / Messenger view. Owns the channel
 * list, the active provider tab and the upsert form, plus the mutation handler
 * extracted verbatim from the legacy `SocialChannelsModule`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useSocialChannelsData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeProvider, setActiveProvider] = useState('instagram_messenger');
  const [form, setForm] = useState(() => emptyForm('instagram_messenger'));
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const refresh = useCallback(() => {
    if (!tenantId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    listMessengerChannels(session, tenantId)
      .then((data) => {
        setChannels(data?.channels || []);
        setError(null);
      })
      .catch((err) =>
        setError(err?.message || 'No se pudieron cargar los canales sociales.'),
      )
      .finally(() => setLoading(false));
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setForm(emptyForm(activeProvider));
    setFeedback(null);
  }, [activeProvider]);

  const currentChannel = useMemo(
    () => channelForProvider(channels, activeProvider),
    [channels, activeProvider],
  );

  const actions = {
    setActiveProvider,
    setFormField: (patch) => setForm((current) => ({ ...current, ...patch })),
    dismissFeedback: () => setFeedback(null),
    async submit() {
      if (!tenantId) return;
      const { payload, error: validationError } = buildPayload(form, activeProvider);
      if (validationError) {
        setFeedback({ kind: 'error', text: validationError });
        return;
      }
      setSubmitting(true);
      setFeedback(null);
      try {
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
    },
  };

  return {
    state: {
      tenantId,
      channels,
      loading,
      error,
      activeProvider,
      form,
      submitting,
      feedback,
      currentChannel,
    },
    actions,
  };
}
