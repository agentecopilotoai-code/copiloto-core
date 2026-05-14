/**
 * UI-008.2 — Campañas: pure data helpers.
 *
 * Status catalogue, segment-filter shape, form shapes, the create/update
 * payload builder, variable parse/serialize and the date formatter — extracted
 * verbatim from the legacy `CampaignsModule` so the table / form drawer /
 * delivery panel share them and they stay unit-testable without React.
 */

/** Spanish labels for each campaign status. */
export const STATUS_LABELS = {
  draft: 'Borrador',
  scheduled: 'Programada',
  running: 'En curso',
  completed: 'Completada',
  cancelled: 'Cancelada',
};

/** `StatusBadge` tone for each campaign status. */
export const STATUS_TONES = {
  draft: 'neutral',
  scheduled: 'accent',
  running: 'warning',
  completed: 'success',
  cancelled: 'danger',
};

/** A blank segment-filter shape (used when no saved segment is picked). */
export const EMPTY_FILTER = {
  tags: [],
  min_appointments: '',
  last_visit_before_days: '',
  last_visit_after_days: '',
  has_upcoming_appointment: '',
};

/** The Spanish label for a campaign status. */
export function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

/** The `StatusBadge` tone for a campaign status. */
export function statusTone(status) {
  return STATUS_TONES[status] || 'neutral';
}

/** Format an ISO date/time for the es-CO locale; `—` when empty. */
export function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

/** Parse a `clave=valor` text block (one per line) into an object. */
export function parseVariables(text) {
  const result = {};
  (text || '').split('\n').forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const idx = trimmed.indexOf('=');
    if (idx === -1) return;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (key) result[key] = value;
  });
  return result;
}

/** Serialize a variables object back into a `clave=valor` text block. */
export function serializeVariables(obj) {
  if (!obj || typeof obj !== 'object') return '';
  return Object.entries(obj)
    .sort((a, b) => {
      const ai = Number.parseInt(a[0], 10);
      const bi = Number.parseInt(b[0], 10);
      if (Number.isFinite(ai) && Number.isFinite(bi)) return ai - bi;
      return a[0].localeCompare(b[0]);
    })
    .map(([k, v]) => `${k}=${v}`)
    .join('\n');
}

/** Build the `segment_filter` payload from the form's segment filters. */
export function buildSegmentPayload(form) {
  const segment = {};
  if (form.tags.length > 0) segment.tags = form.tags;
  if (form.min_appointments !== '' && form.min_appointments !== null)
    segment.min_appointments = Number.parseInt(form.min_appointments, 10);
  if (form.last_visit_before_days !== '' && form.last_visit_before_days !== null)
    segment.last_visit_before_days = Number.parseInt(form.last_visit_before_days, 10);
  if (form.last_visit_after_days !== '' && form.last_visit_after_days !== null)
    segment.last_visit_after_days = Number.parseInt(form.last_visit_after_days, 10);
  if (form.has_upcoming_appointment === 'yes') segment.has_upcoming_appointment = true;
  else if (form.has_upcoming_appointment === 'no') segment.has_upcoming_appointment = false;
  return segment;
}

/** A blank campaign form. */
export function emptyCampaignForm() {
  return {
    name: '',
    template_id: '',
    template_variables: '',
    scheduled_at: '',
    segment_id: '',
    segment: { ...EMPTY_FILTER },
  };
}

/** Build the campaign-form shape from a campaign record. */
export function formFromCampaign(campaign) {
  const segment = campaign.segment_filter || {};
  return {
    name: campaign.name || '',
    template_id: campaign.template_id || '',
    template_variables: serializeVariables(campaign.template_variables),
    scheduled_at: campaign.scheduled_at
      ? new Date(campaign.scheduled_at).toISOString().slice(0, 16)
      : '',
    segment_id: campaign.segment_id || '',
    segment: {
      tags: Array.isArray(segment.tags) ? segment.tags : [],
      min_appointments: segment.min_appointments ?? '',
      last_visit_before_days: segment.last_visit_before_days ?? '',
      last_visit_after_days: segment.last_visit_after_days ?? '',
      has_upcoming_appointment:
        segment.has_upcoming_appointment === true
          ? 'yes'
          : segment.has_upcoming_appointment === false
            ? 'no'
            : '',
    },
  };
}

/**
 * Build the create/update campaign payload from the form. Returns
 * `{ error }` when name or template are missing, otherwise `{ payload }`.
 */
export function buildPayload(form) {
  if (!form.name.trim() || !form.template_id) {
    return { error: 'Nombre y template aprobado son obligatorios.' };
  }
  return {
    payload: {
      name: form.name.trim(),
      template_id: form.template_id || null,
      template_variables: parseVariables(form.template_variables),
      segment_filter: form.segment_id ? {} : buildSegmentPayload(form.segment),
      segment_id: form.segment_id || null,
      scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
    },
  };
}

/** Compute the delivery percentage of a value over a total (0–100, clamped). */
export function deliveryPercent(value, total) {
  return total > 0 ? Math.min(100, Math.round((value / total) * 100)) : 0;
}

/**
 * Derive the four delivery metric rows for a campaign — each row carries the
 * label, the raw counts and the clamped percentage.
 */
export function buildDeliveryMetrics(campaign) {
  if (!campaign) return [];
  const total = campaign.recipient_count || 0;
  return [
    { key: 'sent', label: 'Enviados', value: campaign.sent_count || 0, total, tone: 'accent' },
    {
      key: 'delivered',
      label: 'Entregados',
      value: campaign.delivered_count || 0,
      total,
      tone: 'success',
    },
    { key: 'read', label: 'Leídos', value: campaign.read_count || 0, total, tone: 'accent' },
    { key: 'failed', label: 'Fallidos', value: campaign.failed_count || 0, total, tone: 'danger' },
  ].map((row) => ({ ...row, percent: deliveryPercent(row.value, row.total) }));
}
