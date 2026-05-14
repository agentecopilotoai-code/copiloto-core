/**
 * UI-007.11 — IA · Medios y promociones: pure data helpers.
 *
 * Media-kind catalogue, file-kind inference + size validation, form shapes and
 * promotion payload building — extracted verbatim from the legacy
 * `MediaLibraryModule` so the grid / uploader / promotion drawer share them and
 * they stay unit-testable without React.
 */

/** Spanish labels for each media kind. */
export const MEDIA_KIND_LABELS = {
  image: 'Imagen',
  video: 'Video',
  pdf: 'PDF',
  audio: 'Audio',
};

/** Per-kind size limits in MB (mirror of the backend Meta limits). */
export const SIZE_LIMITS_MB = { image: 5, video: 16, audio: 16, pdf: 100 };

/** `accept` attribute for the upload file picker (Meta-supported mime types). */
export const MEDIA_ACCEPT =
  'image/jpeg,image/png,image/webp,video/mp4,video/3gpp,audio/aac,audio/mp4,audio/mpeg,audio/amr,audio/ogg,application/pdf';

/** Kinds that can be attached to a promotion. */
export const PROMO_MEDIA_KINDS = ['image', 'video', 'pdf'];

/** Infer the media kind from a `File` object's mime type. */
export function inferKindFromFile(file) {
  if (!file) return 'image';
  const type = (file.type || '').toLowerCase();
  if (type.startsWith('image/')) return 'image';
  if (type.startsWith('video/')) return 'video';
  if (type.startsWith('audio/')) return 'audio';
  if (type === 'application/pdf') return 'pdf';
  return 'image';
}

/**
 * Validate a picked file against the per-kind size limit. Returns
 * `{ kind, error }` — `error` is `null` when the file is acceptable.
 */
export function validateUploadFile(file) {
  const kind = inferKindFromFile(file);
  const sizeMb = file.size / (1024 * 1024);
  if (sizeMb > SIZE_LIMITS_MB[kind]) {
    return {
      kind,
      error: `El archivo supera el límite de ${SIZE_LIMITS_MB[kind]} MB para ${MEDIA_KIND_LABELS[kind]}.`,
    };
  }
  return { kind, error: null };
}

/** Derive a default label from a file name (drops the extension). */
export function labelFromFileName(file) {
  if (!file) return '';
  return file.name.split('.').slice(0, -1).join('.') || file.name;
}

/** A blank media-upload form. */
export function emptyUploadForm() {
  return { kind: 'image', label: '', description: '', tags: '', file: null };
}

/** A blank promotion form. */
export function emptyPromoForm() {
  return {
    name: '',
    description: '',
    media_asset_id: '',
    valid_from: '',
    valid_until: '',
    applies_to_service_ids: [],
    coupon_code: '',
    discount_percent: '',
    is_active: true,
    sort_order: 0,
  };
}

/** Build the promotion-form shape from a promotion record. */
export function promoFormFromPromotion(promo) {
  return {
    name: promo.name || '',
    description: promo.description || '',
    media_asset_id: promo.media_asset_id || '',
    valid_from: promo.valid_from ? promo.valid_from.slice(0, 16) : '',
    valid_until: promo.valid_until ? promo.valid_until.slice(0, 16) : '',
    applies_to_service_ids: promo.applies_to_service_ids || [],
    coupon_code: promo.coupon_code || '',
    discount_percent: promo.discount_percent != null ? String(promo.discount_percent) : '',
    is_active: promo.is_active !== false,
    sort_order: promo.sort_order ?? 0,
  };
}

/** Split a comma-separated tag string into a clean array. */
export function parseTags(value) {
  return (value || '')
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/**
 * Build the create/update promotion payload from the form. Returns
 * `{ error }` when the name is missing, otherwise `{ payload }`.
 */
export function buildPromoPayload(form) {
  if (!form.name.trim()) {
    return { error: 'El nombre de la promoción es obligatorio.' };
  }
  return {
    payload: {
      name: form.name.trim(),
      description: form.description.trim() || null,
      media_asset_id: form.media_asset_id || null,
      valid_from: form.valid_from ? new Date(form.valid_from).toISOString() : null,
      valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
      applies_to_service_ids: form.applies_to_service_ids,
      coupon_code: form.coupon_code.trim() || null,
      discount_percent: form.discount_percent === '' ? null : Number(form.discount_percent),
      is_active: form.is_active,
      sort_order: Number(form.sort_order) || 0,
    },
  };
}

/** Human-readable size from a byte count. */
export function formatBytes(bytes) {
  if (bytes == null) return '—';
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(2)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}
