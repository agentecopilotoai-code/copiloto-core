/**
 * UI-INFLU-014 — Helpers puros para el calendario semanal/mensual.
 */

const PERSONA_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#ef4444',
];


export function weekRange(date, locale = 'es-CO') {
  const d = new Date(date);
  // Monday-start week.
  const day = d.getDay() || 7;
  const monday = new Date(d);
  monday.setDate(d.getDate() - day + 1);
  monday.setHours(0, 0, 0, 0);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const fmt = new Intl.DateTimeFormat(locale, { day: '2-digit', month: 'short' });
  return {
    from: monday,
    to: sunday,
    label: `${fmt.format(monday)} – ${fmt.format(sunday)} ${monday.getFullYear()}`,
  };
}


export function groupPostsByDay(posts) {
  const byDay = {};
  for (const p of posts || []) {
    const at = new Date(p.scheduled_at);
    if (Number.isNaN(at.getTime())) continue;
    const key = at.toISOString().slice(0, 10);  // YYYY-MM-DD
    if (!byDay[key]) byDay[key] = [];
    byDay[key].push(p);
  }
  for (const k of Object.keys(byDay)) {
    byDay[k].sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
  }
  return byDay;
}


export function personaColorMap(personas) {
  const map = {};
  (personas || []).forEach((p, i) => {
    map[p.id] = PERSONA_COLORS[i % PERSONA_COLORS.length];
  });
  return map;
}


export function formatTimeSlot(date, locale = 'es-CO') {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(d);
}


export function canApprove(permissions) {
  return Boolean(permissions?.can?.('influencer.posts.approve_publish'));
}


export function buildSchedulePayload(form) {
  return {
    persona_id: form?.persona_id || '',
    generation_id: form?.generation_id || null,
    kind: form?.kind || 'photo',
    caption: String(form?.caption || ''),
    hashtags: Array.isArray(form?.hashtags) ? form.hashtags : [],
    scheduled_at: form?.scheduled_at || new Date().toISOString(),
    platforms: Array.isArray(form?.platforms) ? form.platforms : [],
    mode: form?.mode || 'scheduled',
  };
}
