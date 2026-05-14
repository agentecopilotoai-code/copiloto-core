import {
  ALL_INTENTS_META,
  BOT_EMOJI_OPTIONS,
  BOT_FORMALITY_OPTIONS,
  BOT_TONE_OPTIONS,
  DEFAULT_BOT_PERSONALITY,
  DEFAULT_INTENT_KEYWORDS,
  DEFAULT_NOTIFICATION_SETTINGS,
  defaultPiiRules,
  initialHours,
  weekdays,
} from './tenantSetupData.js';

export function hydrateBotPersonality(raw) {
  let data = raw;
  if (typeof raw === 'string') {
    try { data = JSON.parse(raw); } catch { data = null; }
  }
  if (!data || typeof data !== 'object') return { ...DEFAULT_BOT_PERSONALITY };
  const merged = { ...DEFAULT_BOT_PERSONALITY, ...data };
  if (!BOT_TONE_OPTIONS.some((o) => o.value === merged.tone)) merged.tone = 'neutral';
  if (!BOT_FORMALITY_OPTIONS.some((o) => o.value === merged.formality)) merged.formality = 'tu';
  if (!BOT_EMOJI_OPTIONS.some((o) => o.value === merged.emoji_level)) merged.emoji_level = 'moderate';
  merged.custom_persona = String(merged.custom_persona || '').slice(0, 600);
  return merged;
}

export function renderPersonalityPreview(sample, personality, businessName) {
  let text = sample.base.replace('{business_name}', businessName || 'tu negocio');
  if (personality.formality === 'usted') {
    text = text
      .replace(/\bte\b/gi, 'le')
      .replace(/¿quieres\b/gi, '¿desea')
      .replace(/\bquieres\b/gi, 'desea')
      .replace(/\btu conviene\b/gi, 'le conviene')
      .replace(/\bte conviene\b/gi, 'le conviene')
      .replace(/\b(t|T)u\b/g, (m) => (m === 'tu' ? 'su' : 'Su'));
  } else if (personality.formality === 'vos') {
    text = text
      .replace(/¿quieres\b/gi, '¿querés')
      .replace(/\bquieres\b/gi, 'querés')
      .replace(/\btienes\b/gi, 'tenés');
  }
  if (personality.tone === 'formal') {
    text = text.replace(/^¡Hola!\s*/i, 'Buen día. ').replace(/excelente/gi, 'óptimamente');
  } else if (personality.tone === 'playful') {
    text = text.replace(/^¡Hola!/, '¡Holaaa!');
  }
  const emojiMap = {
    none: { greeting: '', availability: '', objection: '' },
    low: { greeting: ' 👋', availability: '', objection: '' },
    moderate: { greeting: ' 👋😊', availability: ' 📅', objection: ' 💡' },
    high: { greeting: ' 👋😊✨', availability: ' 📅✨', objection: ' 💡✨🙌' },
  };
  const suffix = emojiMap[personality.emoji_level]?.[sample.id] ?? '';
  return `${text}${suffix}`;
}

export function normalizeComplaintAlertChannels(raw) {
  if (!raw || typeof raw !== 'object') {
    return { email: [], whatsapp: [], webhook_url: '' };
  }
  const email = Array.isArray(raw.email)
    ? raw.email.filter((value) => typeof value === 'string' && value.trim()).map((value) => value.trim())
    : [];
  const whatsapp = Array.isArray(raw.whatsapp)
    ? raw.whatsapp.filter((value) => typeof value === 'string' && value.trim()).map((value) => value.trim())
    : [];
  const webhookUrl = typeof raw.webhook_url === 'string' ? raw.webhook_url.trim() : '';
  return { email, whatsapp, webhook_url: webhookUrl };
}

export function hydrateNotificationSettings(raw) {
  const parsed = typeof raw === 'string'
    ? (() => { try { return JSON.parse(raw); } catch { return {}; } })()
    : raw;
  if (!parsed || typeof parsed !== 'object') {
    return { ...DEFAULT_NOTIFICATION_SETTINGS };
  }
  const merged = { ...DEFAULT_NOTIFICATION_SETTINGS, ...parsed };
  merged.complaint_alert_channels = normalizeComplaintAlertChannels(
    merged.complaint_alert_channels,
  );
  return merged;
}

export function defaultIntentSettings() {
  return {
    enabled_intents: ALL_INTENTS_META.map((i) => i.id),
    custom_keywords: DEFAULT_INTENT_KEYWORDS,
    min_confidence: 0.70,
  };
}

export function hydrateIntentSettings(raw) {
  const data = (typeof raw === 'string' ? (() => { try { return JSON.parse(raw); } catch { return {}; } })() : raw) || {};
  // Merge saved keywords with defaults: saved values take precedence, defaults fill gaps.
  const saved = data.custom_keywords || {};
  const merged = { ...DEFAULT_INTENT_KEYWORDS };
  for (const [intent, kws] of Object.entries(saved)) {
    if (Array.isArray(kws) && kws.length > 0) merged[intent] = kws;
  }
  return {
    enabled_intents: data.enabled_intents || ALL_INTENTS_META.map((i) => i.id),
    custom_keywords: merged,
    min_confidence: data.min_confidence ?? 0.70,
  };
}

export function slugifyVertical(label) {
  return (label || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 64);
}

export function cloneInitialHours() {
  return Object.fromEntries(
    weekdays.map(([day]) => [day, { ...initialHours[day] }]),
  );
}

export function jsonObject(value, fallback = {}) {
  if (!value) return fallback;
  if (typeof value === 'string') {
    try {
      return JSON.parse(value);
    } catch {
      return fallback;
    }
  }
  return value;
}

export function formFromBusinessHours(value) {
  const businessHours = jsonObject(value);
  const weeklySchedule = businessHours.weekly_schedule || {};

  return Object.fromEntries(
    weekdays.map(([day]) => {
      const defaultDay = initialHours[day];
      const slots = weeklySchedule[day] || [];
      const firstSlot = slots[0];

      return [
        day,
        {
          enabled: Boolean(firstSlot),
          start: firstSlot?.start || defaultDay.start,
          end: firstSlot?.end || defaultDay.end,
        },
      ];
    }),
  );
}

export function formFromEscalationPolicy(value) {
  const escalationPolicy = jsonObject(value);
  const triggers = escalationPolicy.triggers || {};

  return {
    enabled: escalationPolicy.enabled ?? true,
    queue: escalationPolicy.queue || 'default-support',
    priority: escalationPolicy.priority || 'normal',
    afterBotTurns: triggers.after_bot_turns ?? 5,
    confidenceBelow: triggers.confidence_below ?? 0.55,
    keywords: Array.isArray(triggers.keywords)
      ? triggers.keywords.join(', ')
      : 'humano, asesor, agente, reclamo',
    handoffMessage:
      escalationPolicy.handoff_message ||
      'Te conecto con una persona del equipo para ayudarte mejor.',
    consecutiveNoContextLimit: escalationPolicy.consecutive_no_context_limit ?? 2,
    enforceServiceWindow: escalationPolicy.enforce_service_window ?? true,
    selfServiceMinHoursBeforeStart:
      escalationPolicy.self_service?.min_hours_before_start ?? 2,
  };
}

export function formFromPiiPolicy(value, settings) {
  const piiPolicy = jsonObject(value);

  return {
    mode: piiPolicy.mode || 'balanced',
    retentionDays: piiPolicy.retention_days ?? 180,
    redactBeforeModel: piiPolicy.redact_before_model ?? true,
    logRedaction: piiPolicy.log_redaction ?? true,
    noTrain: settings.no_train ?? true,
    rules: { ...defaultPiiRules, ...(piiPolicy.rules || {}) },
  };
}

export function hydrateSettings(settings) {
  return {
    settingsForm: { locale: settings.locale || 'es-CO' },
    hoursForm: formFromBusinessHours(settings.business_hours),
    escalationForm: formFromEscalationPolicy(settings.escalation_policy),
    privacyForm: formFromPiiPolicy(settings.pii_policy, settings),
    intentSettings: hydrateIntentSettings((settings.escalation_policy || {}).intent_settings),
    notificationSettings: hydrateNotificationSettings(settings.notification_settings),
    botPersonality: hydrateBotPersonality(settings.bot_personality),
  };
}

export function toBusinessHours(hoursForm) {
  return {
    timezone_strategy: 'tenant_timezone',
    weekly_schedule: weekdays.reduce((schedule, [day]) => {
      const item = hoursForm[day];
      schedule[day] = item.enabled ? [{ start: item.start, end: item.end }] : [];
      return schedule;
    }, {}),
  };
}

export function toEscalationPolicy(escalationForm) {
  return {
    enabled: escalationForm.enabled,
    queue: escalationForm.queue,
    priority: escalationForm.priority,
    triggers: {
      after_bot_turns: Number(escalationForm.afterBotTurns),
      confidence_below: Number(escalationForm.confidenceBelow),
      keywords: escalationForm.keywords
        .split(',')
        .map((keyword) => keyword.trim())
        .filter(Boolean),
    },
    handoff_message: escalationForm.handoffMessage,
    consecutive_no_context_limit: Number(escalationForm.consecutiveNoContextLimit),
    enforce_service_window: escalationForm.enforceServiceWindow,
    self_service: {
      min_hours_before_start: Number(escalationForm.selfServiceMinHoursBeforeStart),
    },
  };
}

export function toPiiPolicy(privacyForm) {
  return {
    mode: privacyForm.mode,
    retention_days: Number(privacyForm.retentionDays),
    redact_before_model: privacyForm.redactBeforeModel,
    log_redaction: privacyForm.logRedaction,
    rules: privacyForm.rules,
  };
}

export function formatJson(value) {
  return JSON.stringify(value, null, 2);
}
