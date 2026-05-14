/**
 * UI-007.9 — Canales · Instagram / Messenger: pure data helpers.
 *
 * Provider catalogue, form shape, payload building and the status label —
 * extracted verbatim from the legacy `SocialChannelsModule` so the form /
 * status panels share them and they stay unit-testable without React.
 */

/** The two Meta Messenger surfaces, with their recipient-id label + docs link. */
export const PROVIDER_OPTIONS = [
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

/** A blank channel form for `provider`. */
export function emptyForm(provider) {
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

/** Look up the provider metadata for a provider id. */
export function providerMeta(providerId) {
  return PROVIDER_OPTIONS.find((p) => p.id === providerId) || null;
}

/** Find the configured channel record for a provider, or `null`. */
export function channelForProvider(channels, providerId) {
  return (channels || []).find((c) => c.provider === providerId) || null;
}

/**
 * Status label for a channel: 'sin configurar' when missing, the raw status
 * when not active, otherwise 'live' / 'mock' from the account mode.
 */
export function statusLabel(channel) {
  if (!channel) return 'sin configurar';
  if (channel.status !== 'active') return channel.status;
  return channel.account_mode === 'live' ? 'live' : 'mock';
}

/** `StatusBadge` tone for a channel status label. */
export function statusTone(channel) {
  if (!channel) return 'neutral';
  if (channel.status !== 'active') return 'warning';
  return channel.account_mode === 'live' ? 'success' : 'accent';
}

/** The recipient id stored on a channel record (page or instagram account). */
export function channelRecipientId(channel) {
  if (!channel) return '—';
  return channel.page_id || channel.instagram_account_id || '—';
}

/**
 * Build the upsert payload from the form. Returns `{ error }` when the
 * recipient account id is missing, otherwise `{ payload }`. Secrets are only
 * sent when the user typed them (`undefined` is dropped by the API client).
 */
export function buildPayload(form, provider) {
  if (!form.recipient_account_id.trim()) {
    return { error: 'El identificador de la cuenta es obligatorio.' };
  }
  return {
    payload: {
      provider,
      recipient_account_id: form.recipient_account_id.trim(),
      business_id: form.business_id.trim() || null,
      meta_access_token: form.meta_access_token.trim() || undefined,
      app_secret: form.app_secret.trim() || undefined,
      verify_token: form.verify_token.trim() || undefined,
      account_mode: form.account_mode,
      service_window_hours: Number(form.service_window_hours) || 24,
    },
  };
}
