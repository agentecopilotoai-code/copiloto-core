/**
 * UI-INFLU-005 — Helpers puros para el detalle del estudio del personaje.
 */

const STATUS_LABELS = {
  active: 'Activo',
  paused: 'Pausado',
  draft: 'Borrador',
  archived: 'Archivado',
};


export function statusLabel(status) {
  return STATUS_LABELS[status] || status || 'Sin estado';
}


/**
 * Construye una etiqueta "ACTIVO · 12 PROGRAMADOS" a partir del status
 * y el scheduled_count. Si no hay programados, omite la segunda parte.
 */
export function formatScheduledCount(status, scheduled) {
  const upper = statusLabel(status).toUpperCase();
  const n = Number(scheduled) || 0;
  if (n <= 0) return upper;
  return `${upper} · ${n} PROGRAMADO${n === 1 ? '' : 'S'}`;
}


/**
 * Etiqueta "Próximo post · 11:00 mañana · IG, YT" a partir del shape
 * `{at, kind, platforms}`. Si no hay próximo, devuelve null.
 *
 * Si la fecha es hoy → "HH:mm hoy"; mañana → "HH:mm mañana"; sino la
 * fecha localizada `dd MMM`. Acepta un `now` inyectado (testeabilidad).
 */
export function nextPostLabel(next, now = new Date()) {
  if (!next?.at) return null;
  const at = next.at instanceof Date ? next.at : new Date(next.at);
  if (Number.isNaN(at.getTime())) return null;

  const startOfDay = (d) => {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
  };
  const today = startOfDay(now);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const target = startOfDay(at);

  const hh = String(at.getHours()).padStart(2, '0');
  const mm = String(at.getMinutes()).padStart(2, '0');
  let whenLabel;
  if (target.getTime() === today.getTime()) whenLabel = 'hoy';
  else if (target.getTime() === tomorrow.getTime()) whenLabel = 'mañana';
  else whenLabel = at.toLocaleDateString('es-CO', { day: '2-digit', month: 'short' });

  const platforms = (next.platforms ?? []).map((p) => p.toUpperCase()).join(', ');
  const head = `${hh}:${mm} ${whenLabel}`;
  return platforms ? `${head} · ${platforms}` : head;
}


/**
 * Extrae los chips de identidad/voz a partir del jsonb voice del persona.
 * Recibe `{tone, formality, style_tokens}` y devuelve una lista de strings.
 */
export function tagsFromVoice(voice = {}) {
  const tags = [];
  if (voice.tone) tags.push(capitalize(voice.tone));
  if (voice.formality && voice.formality !== 'neutral') {
    tags.push(capitalize(voice.formality));
  }
  if (Array.isArray(voice.style_tokens)) {
    for (const t of voice.style_tokens) {
      if (t) tags.push(capitalize(t));
    }
  }
  return tags;
}


function capitalize(s) {
  const str = String(s);
  return str.charAt(0).toUpperCase() + str.slice(1);
}
