import { useEffect, useMemo, useState } from 'react';

import QualificationQuestionsPanel from './QualificationQuestionsPanel.jsx';
import { BranchesModule } from '../branches/BranchesModule.jsx';
import {
  createContactTag,
  createTenant,
  deleteContactTag,
  getTenant,
  getTenantPaymentSettings,
  getTenantSettings,
  listAuditLogs,
  listContactTags,
  patchTenantStatus,
  reindexAllKnowledgeDocuments,
  updateContactTag,
  updateTenant,
  updateTenantPaymentSettings,
  updateTenantSettings,
} from '../../../services/coreApi.js';

const wizardTabs = [
  { id: 'tenant', label: 'Negocio' },
  { id: 'calificacion', label: 'Calificación' },
  { id: 'settings', label: 'Settings' },
  { id: 'hours', label: 'Horarios' },
  { id: 'branches', label: 'Sedes' },
  { id: 'escalation', label: 'Escalamiento' },
  { id: 'intenciones', label: 'Intenciones' },
  { id: 'notificaciones', label: 'Notificaciones' },
  { id: 'pagos', label: 'Pagos' },
  { id: 'privacy', label: 'Privacidad' },
  { id: 'ia_rag', label: 'IA y RAG' },
  { id: 'audit', label: 'Auditoría' },
];

const DEFAULT_NOTIFICATION_SETTINGS = {
  confirmation_enabled: true,
  reminder_24h_enabled: true,
  reminder_1h_enabled: false,
  include_location_link: true,
  location_address: '',
  location_maps_url: '',
  include_preparation_notes: true,
  no_show_confirmation_enabled: true,
  confirmation_reminder_hours: 4,
  post_instructions_enabled: true,
  post_instructions_delay_minutes: 30,
  post_feedback_enabled: true,
  post_feedback_delay_hours: 2,
  post_rebooking_enabled: false,
  post_rebooking_delay_days: 30,
  post_rebooking_message: '',
  auto_rebook_on_decline: true,
  vip_budget_threshold: 0,
  ask_referrer: false,
};

function hydrateNotificationSettings(raw) {
  const parsed = typeof raw === 'string'
    ? (() => { try { return JSON.parse(raw); } catch { return {}; } })()
    : raw;
  if (!parsed || typeof parsed !== 'object') {
    return { ...DEFAULT_NOTIFICATION_SETTINGS };
  }
  return { ...DEFAULT_NOTIFICATION_SETTINGS, ...parsed };
}

const ALL_INTENTS_META = [
  { id: 'greeting', label: 'Saludo', description: 'Apertura o reapertura de conversación.' },
  { id: 'faq', label: 'FAQ', description: 'Pregunta informativa (precios, horarios, servicios).' },
  { id: 'book_appointment', label: 'Agendar cita', description: 'Quiere agendar una cita nueva.' },
  { id: 'confirm_appointment', label: 'Confirmar cita', description: 'Consulta o confirma una cita existente.' },
  { id: 'reschedule_appointment', label: 'Reagendar cita', description: 'Quiere mover una cita a otro horario.' },
  { id: 'cancel_appointment', label: 'Cancelar cita', description: 'Quiere cancelar una cita.' },
  { id: 'check_availability', label: 'Consultar disponibilidad', description: 'Pregunta por disponibilidad sin comprometerse.' },
  { id: 'complaint_or_risk', label: 'Queja / Riesgo', description: 'Queja, reclamación o frustración — fuerza handoff.' },
  { id: 'out_of_scope', label: 'Fuera de scope', description: 'Mensaje sin relación con el negocio.' },
  { id: 'opt_out', label: 'Opt-out', description: 'El usuario pide no recibir más mensajes.' },
];

const DEFAULT_INTENT_KEYWORDS = {
  greeting: ['hola', 'buenos días', 'buenas tardes', 'buenas noches', 'hey', 'saludos', 'buen día'],
  faq: ['información', 'cuánto cuesta', 'precio', 'horario', 'cómo funciona', 'qué ofrecen', 'dónde están'],
  book_appointment: ['quiero una cita', 'agendar', 'reservar', 'turno', 'appointment', 'necesito cita', 'pedir hora'],
  confirm_appointment: ['confirmar', 'confirmación', 'tengo cita', 'mi cita', 'está agendado', 'queda confirmada'],
  reschedule_appointment: ['reagendar', 'cambiar cita', 'mover cita', 'otro horario', 'reprogramar', 'otra fecha'],
  cancel_appointment: ['cancelar', 'cancela mi cita', 'no puedo ir', 'ya no quiero', 'quiero cancelar'],
  check_availability: ['disponibilidad', 'tienen lugar', 'hay espacio', 'qué días tienen', 'qué horarios tienen'],
  complaint_or_risk: ['queja', 'reclamo', 'estafa', 'fraude', 'mal servicio', 'indignado', 'insatisfecho', 'terrible', 'pésimo'],
  out_of_scope: [],
  opt_out: ['stop', 'baja', 'no me escribas', 'no quiero mensajes', 'cancelar suscripción', 'darme de baja'],
};

function defaultIntentSettings() {
  return {
    enabled_intents: ALL_INTENTS_META.map((i) => i.id),
    custom_keywords: DEFAULT_INTENT_KEYWORDS,
    min_confidence: 0.70,
  };
}

function hydrateIntentSettings(raw) {
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

const embeddingProviderOptions = [
  {
    value: 'local_hash',
    label: 'Local hash (sin API)',
    description: 'SHA-256 determinístico. No requiere API key. Útil solo para desarrollo; la búsqueda semántica no funciona.',
    defaultModel: 'copilotoia-local-hash-v1',
    defaultDims: 1536,
  },
  {
    value: 'openai',
    label: 'OpenAI',
    description: 'text-embedding-3-small (1536 dims) o text-embedding-3-large (3072 dims). Requiere API key de OpenAI.',
    defaultModel: 'text-embedding-3-small',
    defaultDims: 1536,
  },
  {
    value: 'anthropic',
    label: 'Anthropic / Voyage',
    description: 'voyage-3-lite (1024 dims) via Voyage AI. Requiere API key de Voyage (api.voyageai.com).',
    defaultModel: 'voyage-3-lite',
    defaultDims: 1024,
  },
  {
    value: 'ollama',
    label: 'Ollama (local)',
    description: 'Modelo de embeddings local via Ollama. Sin costo de API; requiere Ollama corriendo en el servidor.',
    defaultModel: 'nomic-embed-text',
    defaultDims: 768,
  },
];

const weekdays = [
  ['mon', 'Lunes'],
  ['tue', 'Martes'],
  ['wed', 'Miércoles'],
  ['thu', 'Jueves'],
  ['fri', 'Viernes'],
  ['sat', 'Sábado'],
  ['sun', 'Domingo'],
];

const initialHours = weekdays.reduce((hours, [day], index) => {
  hours[day] = { enabled: index < 5, start: '09:00', end: '18:00' };
  return hours;
}, {});

const defaultPiiRules = {
  phone: 'mask',
  email: 'mask',
  address: 'redact',
  government_id: 'redact',
};

function slugifyVertical(label) {
  return (label || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 64);
}


function cloneInitialHours() {
  return Object.fromEntries(
    weekdays.map(([day]) => [day, { ...initialHours[day] }]),
  );
}

function jsonObject(value, fallback = {}) {
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

function formFromBusinessHours(value) {
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

function formFromEscalationPolicy(value) {
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

function formFromPiiPolicy(value, settings) {
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

function hydrateSettings(settings) {
  return {
    settingsForm: { locale: settings.locale || 'es-CO' },
    hoursForm: formFromBusinessHours(settings.business_hours),
    escalationForm: formFromEscalationPolicy(settings.escalation_policy),
    privacyForm: formFromPiiPolicy(settings.pii_policy, settings),
    intentSettings: hydrateIntentSettings((settings.escalation_policy || {}).intent_settings),
    notificationSettings: hydrateNotificationSettings(settings.notification_settings),
  };
}

function toBusinessHours(hoursForm) {
  return {
    timezone_strategy: 'tenant_timezone',
    weekly_schedule: weekdays.reduce((schedule, [day]) => {
      const item = hoursForm[day];
      schedule[day] = item.enabled ? [{ start: item.start, end: item.end }] : [];
      return schedule;
    }, {}),
  };
}

function toEscalationPolicy(escalationForm) {
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

function toPiiPolicy(privacyForm) {
  return {
    mode: privacyForm.mode,
    retention_days: Number(privacyForm.retentionDays),
    redact_before_model: privacyForm.redactBeforeModel,
    log_redaction: privacyForm.logRedaction,
    rules: privacyForm.rules,
  };
}

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

export function TenantSetupWizard({ module, onTenantCreated, session, tenant, initialTab }) {
  const [activeTab, setActiveTab] = useState(initialTab || 'tenant');
  const [tenantForm, setTenantForm] = useState({
    slug: 'tenant-demo',
    legal_name: 'Tenant Demo S.A.S.',
    display_name: 'Tenant Demo',
    business_type_label: '',
    vertical_code: '',
    country_code: 'CO',
    timezone: 'America/Bogota',
  });
  const [settingsForm, setSettingsForm] = useState({ locale: 'es-CO' });
  const [hoursForm, setHoursForm] = useState(cloneInitialHours);
  const [escalationForm, setEscalationForm] = useState({
    enabled: true,
    queue: 'default-support',
    priority: 'normal',
    afterBotTurns: 5,
    confidenceBelow: 0.55,
    keywords: 'humano, asesor, agente, reclamo',
    handoffMessage: 'Te conecto con una persona del equipo para ayudarte mejor.',
    consecutiveNoContextLimit: 2,
    enforceServiceWindow: true,
  });
  const [intentSettings, setIntentSettings] = useState(defaultIntentSettings);
  const [notificationSettings, setNotificationSettings] = useState(() => ({ ...DEFAULT_NOTIFICATION_SETTINGS }));
  const [privacyForm, setPrivacyForm] = useState({
    mode: 'balanced',
    retentionDays: 180,
    redactBeforeModel: true,
    logRedaction: true,
    noTrain: true,
    rules: defaultPiiRules,
  });
  const [auditLogs, setAuditLogs] = useState([]);
  const [lastSettings, setLastSettings] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [tenantStatus, setTenantStatus] = useState(null);
  const [statusReason, setStatusReason] = useState('');
  const [targetStatus, setTargetStatus] = useState('active');
  const [ragForm, setRagForm] = useState({
    provider: 'local_hash',
    model: 'copilotoia-local-hash-v1',
    apiKey: '',
    dimensions: 1536,
  });
  const [reindexResult, setReindexResult] = useState(null);
  const [contactTags, setContactTags] = useState([]);
  const [tagForm, setTagForm] = useState({ name: '', color: '#4f6ef7', description: '' });
  const [editingTagId, setEditingTagId] = useState(null);
  const [paymentSettings, setPaymentSettings] = useState({
    provider: 'none',
    currency: 'COP',
    default_amount: '',
    api_key_configured: false,
    webhook_secret_configured: false,
  });
  const [paymentForm, setPaymentForm] = useState({ apiKey: '', webhookSecret: '' });

  const settingsPayload = useMemo(
    () => ({
      locale: settingsForm.locale,
      business_hours: toBusinessHours(hoursForm),
      escalation_policy: {
        ...toEscalationPolicy(escalationForm),
        intent_settings: intentSettings,
      },
      pii_policy: toPiiPolicy(privacyForm),
      no_train: privacyForm.noTrain,
      notification_settings: notificationSettings,
    }),
    [escalationForm, hoursForm, intentSettings, notificationSettings, privacyForm, settingsForm.locale],
  );

  const currentTenantId = tenant?.id;

  useEffect(() => {
    let mounted = true;

    if (!currentTenantId) return undefined;

    Promise.all([getTenant(session, currentTenantId), getTenantSettings(session, currentTenantId)])
      .then(([tenantDetails, loadedSettings]) => {
        if (!mounted) return;
        setTenantForm({
          slug: tenantDetails.slug || '',
          legal_name: tenantDetails.legal_name || '',
          display_name: tenantDetails.display_name || '',
          business_type_label: tenantDetails.business_type_label || '',
          vertical_code: tenantDetails.vertical_code || '',
          country_code: tenantDetails.country_code || 'CO',
          timezone: tenantDetails.timezone || 'America/Bogota',
        });
        setTenantStatus(tenantDetails.status || null);

        const hydrated = hydrateSettings(loadedSettings);
        setSettingsForm(hydrated.settingsForm);
        setHoursForm(hydrated.hoursForm);
        setEscalationForm(hydrated.escalationForm);
        setPrivacyForm(hydrated.privacyForm);
        setIntentSettings(hydrated.intentSettings);
        setNotificationSettings(hydrated.notificationSettings);
        setLastSettings(loadedSettings);
      })
      .catch(() => {
        // Keep editable defaults if tenant details or settings cannot be loaded.
      });

    return () => {
      mounted = false;
    };
  }, [currentTenantId, session]);

  async function runAction(action, successMessage) {
    setIsBusy(true);
    setNotice(null);
    try {
      const result = await action();
      setNotice({ type: 'success', text: successMessage });
      return result;
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
      return null;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSaveTenant(event) {
    event.preventDefault();
    const saveTenant = currentTenantId
      ? () => updateTenant(session, currentTenantId, tenantForm)
      : () => createTenant(session, tenantForm);
    const saved = await runAction(
      saveTenant,
      currentTenantId ? 'Tenant actualizado y registrado en auditoría.' : 'Tenant creado y registrado en auditoría.',
    );
    if (saved) {
      onTenantCreated?.({
        ...saved,
        id: saved.id,
        label: `${saved.slug} · ${saved.id}`,
      });
      setActiveTab('settings');
    }
  }

  async function handleSaveSettings(event) {
    event.preventDefault();
    if (!currentTenantId) {
      setNotice({ type: 'error', text: 'Selecciona o crea un tenant antes de guardar settings.' });
      return;
    }
    const updated = await runAction(
      () => updateTenantSettings(session, currentTenantId, settingsPayload),
      'Settings guardados y auditados.',
    );
    if (updated) {
      setLastSettings(updated);
      setActiveTab('audit');
      await refreshAuditLogs(currentTenantId, false);
    }
  }

  const availableStatusTransitions = {
    trial: [{ value: 'active', label: 'Activar (trial → active)' }, { value: 'suspended', label: 'Suspender (trial → suspended)' }, { value: 'churned', label: 'Dar de baja (trial → churned)' }],
    active: [{ value: 'suspended', label: 'Suspender (active → suspended)' }, { value: 'churned', label: 'Dar de baja (active → churned)' }],
    suspended: [{ value: 'active', label: 'Reactivar (suspended → active)' }, { value: 'churned', label: 'Dar de baja (suspended → churned)' }],
    churned: [],
  };

  async function handleChangeStatus(event) {
    event.preventDefault();
    if (!currentTenantId) return;
    const updated = await runAction(
      () => patchTenantStatus(session, currentTenantId, targetStatus, statusReason),
      `Estado cambiado a "${targetStatus}" y registrado en auditoría.`,
    );
    if (updated) {
      setTenantStatus(updated.status);
      setStatusReason('');
      await refreshAuditLogs(currentTenantId, false);
    }
  }

  function handleProviderChange(provider) {
    const option = embeddingProviderOptions.find((opt) => opt.value === provider);
    setRagForm((current) => ({
      ...current,
      provider,
      model: option?.defaultModel || current.model,
      dimensions: option?.defaultDims || current.dimensions,
    }));
  }

  async function handleReindexAll(event) {
    event.preventDefault();
    if (!currentTenantId) return;
    setReindexResult(null);
    const result = await runAction(
      () => reindexAllKnowledgeDocuments(session, currentTenantId),
      `Re-indexación completada: ${0} documentos procesados.`,
    );
    if (result) {
      setReindexResult(result);
      setNotice({
        type: result.failed === 0 ? 'success' : 'info',
        text: `Re-indexación completada: ${result.indexed} indexados, ${result.failed} fallidos con proveedor "${result.embedding_provider}".`,
      });
    }
  }

  async function refreshContactTags(tenantId = currentTenantId, showNotice = false) {
    if (!tenantId) return;
    try {
      const tags = await listContactTags(session, tenantId);
      setContactTags(tags || []);
      if (showNotice) setNotice({ type: 'success', text: 'Etiquetas recargadas.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    }
  }

  useEffect(() => {
    if (!currentTenantId) return;
    refreshContactTags(currentTenantId);
  }, [currentTenantId]);

  useEffect(() => {
    if (!currentTenantId) return;
    let mounted = true;
    getTenantPaymentSettings(session, currentTenantId)
      .then((data) => {
        if (!mounted) return;
        setPaymentSettings({
          provider: data.provider || 'none',
          currency: data.currency || 'COP',
          default_amount: data.default_amount ?? '',
          api_key_configured: Boolean(data.api_key_configured),
          webhook_secret_configured: Boolean(data.webhook_secret_configured),
        });
        setPaymentForm({ apiKey: '', webhookSecret: '' });
      })
      .catch(() => {
        // Keep defaults if the call fails.
      });
    return () => {
      mounted = false;
    };
  }, [currentTenantId, session]);

  async function handleSavePaymentSettings(event) {
    event.preventDefault();
    if (!currentTenantId) return;
    const payload = {
      provider: paymentSettings.provider,
      currency: (paymentSettings.currency || 'COP').toUpperCase(),
      default_amount: paymentSettings.default_amount === '' || paymentSettings.default_amount === null
        ? null
        : Number(paymentSettings.default_amount),
      api_key: paymentForm.apiKey || null,
      webhook_secret: paymentForm.webhookSecret || null,
    };
    const updated = await runAction(
      () => updateTenantPaymentSettings(session, currentTenantId, payload),
      'Configuración de pagos guardada.',
    );
    if (updated) {
      setPaymentSettings({
        provider: updated.provider || 'none',
        currency: updated.currency || 'COP',
        default_amount: updated.default_amount ?? '',
        api_key_configured: Boolean(updated.api_key_configured),
        webhook_secret_configured: Boolean(updated.webhook_secret_configured),
      });
      setPaymentForm({ apiKey: '', webhookSecret: '' });
    }
  }

  async function handleSaveTag(event) {
    event.preventDefault();
    if (!currentTenantId || !tagForm.name.trim()) return;
    const payload = {
      name: tagForm.name.trim(),
      color: tagForm.color || null,
      description: tagForm.description || null,
    };
    const action = editingTagId
      ? () => updateContactTag(session, currentTenantId, editingTagId, payload)
      : () => createContactTag(session, currentTenantId, payload);
    const saved = await runAction(action, editingTagId ? 'Etiqueta actualizada.' : 'Etiqueta creada.');
    if (saved) {
      setTagForm({ name: '', color: '#4f6ef7', description: '' });
      setEditingTagId(null);
      await refreshContactTags();
    }
  }

  async function handleDeleteTag(tagId) {
    if (!currentTenantId) return;
    const ok = await runAction(
      () => deleteContactTag(session, currentTenantId, tagId),
      'Etiqueta eliminada.',
    );
    if (ok !== null) await refreshContactTags();
  }

  function startEditingTag(tag) {
    setEditingTagId(tag.id);
    setTagForm({
      name: tag.name,
      color: tag.color || '#4f6ef7',
      description: tag.description || '',
    });
  }

  function cancelEditingTag() {
    setEditingTagId(null);
    setTagForm({ name: '', color: '#4f6ef7', description: '' });
  }

  async function refreshAuditLogs(tenantId = currentTenantId, showNotice = true) {
    if (!tenantId) return;
    const logs = await runAction(
      () => listAuditLogs(session, tenantId),
      showNotice ? 'Auditoría actualizada.' : 'Settings guardados y auditados.',
    );
    if (logs) setAuditLogs(logs);
  }

  return (
    <section className="module-card wizard-card">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Wizard MVP</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label || 'Sin tenant seleccionado'}</strong>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Secciones del wizard">
        {wizardTabs.map((tab) => (
          <button
            aria-selected={activeTab === tab.id}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}

      {activeTab === 'tenant' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveTenant}>
          <label>
            Slug
            <input value={tenantForm.slug} onChange={(event) => setTenantForm({ ...tenantForm, slug: event.target.value })} required />
          </label>
          <label>
            Razón social
            <input value={tenantForm.legal_name} onChange={(event) => setTenantForm({ ...tenantForm, legal_name: event.target.value })} required />
          </label>
          <label>
            Nombre visible
            <input value={tenantForm.display_name} onChange={(event) => setTenantForm({ ...tenantForm, display_name: event.target.value })} required />
          </label>
          <label>
            Tipo de negocio
            <input
              placeholder="Ej. Clínica dental, Spa, Taller mecánico"
              value={tenantForm.business_type_label}
              onChange={(event) => {
                const label = event.target.value;
                setTenantForm({
                  ...tenantForm,
                  business_type_label: label,
                  vertical_code: tenantForm.vertical_code || slugifyVertical(label),
                });
              }}
              maxLength={160}
              required
            />
          </label>
          <label>
            Clave técnica (vertical_code)
            <input
              placeholder="Ej. dental, spa, taller"
              value={tenantForm.vertical_code}
              onChange={(event) => setTenantForm({ ...tenantForm, vertical_code: event.target.value })}
              maxLength={64}
              required
            />
          </label>
          <label>
            País
            <input value={tenantForm.country_code} onChange={(event) => setTenantForm({ ...tenantForm, country_code: event.target.value.toUpperCase() })} required maxLength={2} />
          </label>
          <label>
            Zona horaria
            <input value={tenantForm.timezone} onChange={(event) => setTenantForm({ ...tenantForm, timezone: event.target.value })} required />
          </label>
          <div className="form-actions">
            <button className="primary-action" disabled={isBusy} type="submit">{currentTenantId ? 'Actualizar tenant' : 'Crear tenant'}</button>
          </div>
        </form>
      ) : null}

      {activeTab === 'tenant' && currentTenantId ? (
        <div className="wizard-panel">
          <h3>Etiquetas de contacto</h3>
          <p className="hint">
            Define las etiquetas disponibles para clasificar contactos del CRM (ej. VIP, Nuevo, En tratamiento).
          </p>
          <form className="form-grid" onSubmit={handleSaveTag}>
            <label>
              Nombre
              <input
                value={tagForm.name}
                onChange={(event) => setTagForm({ ...tagForm, name: event.target.value })}
                maxLength={80}
                placeholder="Ej. VIP"
                required
              />
            </label>
            <label>
              Color
              <input
                type="color"
                value={tagForm.color}
                onChange={(event) => setTagForm({ ...tagForm, color: event.target.value })}
              />
            </label>
            <label className="wide">
              Descripción
              <input
                value={tagForm.description}
                onChange={(event) => setTagForm({ ...tagForm, description: event.target.value })}
                maxLength={500}
                placeholder="Opcional"
              />
            </label>
            <div className="form-actions">
              <button className="primary-action" type="submit" disabled={isBusy || !tagForm.name.trim()}>
                {editingTagId ? 'Actualizar etiqueta' : 'Crear etiqueta'}
              </button>
              {editingTagId ? (
                <button className="secondary-action" type="button" onClick={cancelEditingTag}>
                  Cancelar edición
                </button>
              ) : null}
            </div>
          </form>
          {contactTags.length ? (
            <ul style={{ listStyle: 'none', padding: 0, marginTop: '1rem' }}>
              {contactTags.map((tag) => (
                <li
                  key={tag.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.6rem',
                    padding: '0.4rem 0',
                    borderBottom: '1px solid var(--border, #e2e8f0)',
                  }}
                >
                  <span
                    className="status-pill"
                    style={{ background: tag.color || '#4f6ef7', color: '#fff', padding: '0.15rem 0.6rem' }}
                  >
                    {tag.name}
                  </span>
                  <span className="hint" style={{ flex: 1 }}>{tag.description || '—'}</span>
                  <span className="hint">{tag.contacts_count ?? 0} contactos</span>
                  <button className="secondary-action" type="button" onClick={() => startEditingTag(tag)}>
                    Editar
                  </button>
                  <button className="secondary-action" type="button" onClick={() => handleDeleteTag(tag.id)}>
                    Eliminar
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Aún no hay etiquetas configuradas.</p>
          )}
        </div>
      ) : null}

      {activeTab === 'tenant' && currentTenantId && tenantStatus ? (
        <div className="wizard-panel status-panel">
          <h3>Estado del tenant</h3>
          <div className="status-current">
            <span>Estado actual:</span>
            <span className={`status-badge status-${tenantStatus}`}>{tenantStatus}</span>
          </div>
          <p className="hint">
            {tenantStatus === 'trial' && 'El tenant está en trial. Actívalo cuando cumpla los prerrequisitos de go-live.'}
            {tenantStatus === 'active' && 'Tenant activo y operando en producción.'}
            {tenantStatus === 'suspended' && 'Tenant suspendido temporalmente. Puedes reactivarlo cuando el problema esté resuelto.'}
            {tenantStatus === 'churned' && 'Tenant dado de baja definitivamente. No se puede transicionar a otro estado.'}
          </p>
          {(availableStatusTransitions[tenantStatus] || []).length > 0 ? (
            <form className="form-grid" onSubmit={handleChangeStatus}>
              <label>
                Nuevo estado
                <select value={targetStatus} onChange={(e) => setTargetStatus(e.target.value)}>
                  {availableStatusTransitions[tenantStatus].map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </label>
              <label className="wide">
                Razón (obligatoria)
                <input
                  placeholder="Ej: Prerrequisitos verificados, aprobado para go-live"
                  required
                  value={statusReason}
                  onChange={(e) => setStatusReason(e.target.value)}
                />
              </label>
              <div className="form-actions">
                <button className="primary-action" disabled={isBusy || !statusReason.trim()} type="submit">Cambiar estado</button>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}

      {activeTab === 'calificacion' ? (
        <div className="wizard-panel">
          <form className="form-grid" onSubmit={handleSaveSettings}>
            <label>
              Umbral VIP (presupuesto)
              <input
                type="number"
                min="0"
                step="1000"
                value={notificationSettings.vip_budget_threshold ?? 0}
                onChange={(e) =>
                  setNotificationSettings({
                    ...notificationSettings,
                    vip_budget_threshold: Number(e.target.value) || 0,
                  })
                }
              />
              <small className="hint">
                Cuando el cliente elige un rango de presupuesto con valor numérico
                ≥ este umbral, recibe la etiqueta automática "VIP". Deja en 0 para
                desactivar.
              </small>
            </label>
            <div className="form-actions">
              <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
                Guardar umbral VIP
              </button>
            </div>
          </form>
          <QualificationQuestionsPanel
            session={session}
            tenantId={currentTenantId}
            onNotice={setNotice}
          />
        </div>
      ) : null}

      {activeTab === 'settings' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
          <label>
            Locale del tenant
            <input value={settingsForm.locale} onChange={(event) => setSettingsForm({ locale: event.target.value })} required />
          </label>
          <div className="builder-preview">
            <strong>Payload construido por el formulario</strong>
            <pre>{formatJson({ locale: settingsPayload.locale })}</pre>
          </div>
          <div className="form-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar configuración completa</button>
          </div>
        </form>
      ) : null}

      {activeTab === 'hours' ? (
        <form className="wizard-panel" onSubmit={handleSaveSettings}>
          <div className="hours-grid">
            {weekdays.map(([day, label]) => (
              <fieldset className="day-card" key={day}>
                <legend>{label}</legend>
                <label className="inline-check">
                  <input checked={hoursForm[day].enabled} onChange={(event) => setHoursForm({ ...hoursForm, [day]: { ...hoursForm[day], enabled: event.target.checked } })} type="checkbox" />
                  Activo
                </label>
                <label>
                  Inicio
                  <input value={hoursForm[day].start} onChange={(event) => setHoursForm({ ...hoursForm, [day]: { ...hoursForm[day], start: event.target.value } })} type="time" />
                </label>
                <label>
                  Fin
                  <input value={hoursForm[day].end} onChange={(event) => setHoursForm({ ...hoursForm, [day]: { ...hoursForm[day], end: event.target.value } })} type="time" />
                </label>
              </fieldset>
            ))}
          </div>
          <div className="form-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar horarios</button>
          </div>
        </form>
      ) : null}

      {activeTab === 'branches' ? (
        <section className="wizard-panel" data-wizard-tab="branches">
          <p className="hint">
            Configura una sede para empezar. Si tu negocio opera en varias ubicaciones, agrega más
            desde el módulo <strong>Sedes</strong> en el menú principal. El bot ofrecerá la
            selección de sede al cliente cuando exista más de una activa.
          </p>
          {currentTenantId ? (
            <BranchesModule
              module={{ label: 'Sedes', summary: 'Configura las ubicaciones físicas del tenant.' }}
              session={session}
              tenant={{ id: currentTenantId }}
            />
          ) : (
            <p>Primero guarda los datos del negocio para configurar sedes.</p>
          )}
        </section>
      ) : null}

      {activeTab === 'escalation' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
          <label className="inline-check wide">
            <input checked={escalationForm.enabled} onChange={(event) => setEscalationForm({ ...escalationForm, enabled: event.target.checked })} type="checkbox" />
            Habilitar escalamiento humano
          </label>
          <label>Cola<input value={escalationForm.queue} onChange={(event) => setEscalationForm({ ...escalationForm, queue: event.target.value })} /></label>
          <label>Prioridad<select value={escalationForm.priority} onChange={(event) => setEscalationForm({ ...escalationForm, priority: event.target.value })}><option>low</option><option>normal</option><option>high</option></select></label>
          <label>
            Máximo de turnos del bot antes de escalar (triggers.after_bot_turns)
            <input min="1" max="50" value={escalationForm.afterBotTurns} onChange={(event) => setEscalationForm({ ...escalationForm, afterBotTurns: event.target.value })} type="number" />
          </label>
          <label>
            Respuestas sin contexto antes de escalar
            <input min="1" max="20" value={escalationForm.consecutiveNoContextLimit} onChange={(event) => setEscalationForm({ ...escalationForm, consecutiveNoContextLimit: event.target.value })} type="number" />
          </label>
          <label>Confianza menor a<input max="1" min="0" step="0.01" value={escalationForm.confidenceBelow} onChange={(event) => setEscalationForm({ ...escalationForm, confidenceBelow: event.target.value })} type="number" /></label>
          <label className="wide">
            Keywords de escalamiento — fuerzan handoff inmediato (separadas por coma)
            <input
              placeholder="humano, asesor, demanda, fraude"
              value={escalationForm.keywords}
              onChange={(event) => setEscalationForm({ ...escalationForm, keywords: event.target.value })}
            />
          </label>
          <label className="inline-check wide">
            <input
              type="checkbox"
              checked={escalationForm.enforceServiceWindow}
              onChange={(event) => setEscalationForm({ ...escalationForm, enforceServiceWindow: event.target.checked })}
            />
            Forzar handoff si la ventana de servicio WhatsApp (24 h) expiró
          </label>
          <label className="wide">Mensaje de handoff<textarea value={escalationForm.handoffMessage} onChange={(event) => setEscalationForm({ ...escalationForm, handoffMessage: event.target.value })} /></label>
          <label>
            Self-service: horas mínimas antes de la cita
            <input
              type="number"
              min="0"
              max="72"
              step="0.5"
              value={escalationForm.selfServiceMinHoursBeforeStart}
              onChange={(event) =>
                setEscalationForm({
                  ...escalationForm,
                  selfServiceMinHoursBeforeStart: event.target.value,
                })
              }
            />
            <small className="hint">
              Si el cliente pide cancelar o reagendar a menos horas de inicio que esto, el bot
              escala a un humano en lugar de actuar (default 2h).
            </small>
          </label>
          <div className="form-actions"><button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar escalamiento</button></div>
        </form>
      ) : null}

      {activeTab === 'intenciones' ? (
        <form className="wizard-panel" onSubmit={handleSaveSettings}>
          <p className="hint" style={{ marginBottom: '1rem' }}>
            Habilita o deshabilita intenciones por tenant y agrega keywords personalizadas adicionales
            a las globales del sistema. El umbral de confianza mínima controla cuándo el bot escala
            al agente humano por incertidumbre.
          </p>

          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <strong>Umbral de confianza mínima</strong>
              <input
                type="range"
                min="0.50"
                max="0.90"
                step="0.01"
                value={intentSettings.min_confidence}
                onChange={(e) => setIntentSettings({ ...intentSettings, min_confidence: Number(e.target.value) })}
                style={{ flex: 1 }}
              />
              <span className="status-badge active">{intentSettings.min_confidence.toFixed(2)}</span>
            </label>
            <p className="hint">Rango 0.50–0.90 · default 0.70. Por debajo de este valor el bot escala al agente.</p>
          </div>

          <div className="intent-list">
            {ALL_INTENTS_META.map((meta) => {
              const enabled = intentSettings.enabled_intents.includes(meta.id);
              const kws = (intentSettings.custom_keywords[meta.id] || []).join(', ');
              return (
                <fieldset key={meta.id} className="intent-card" style={{ border: '1px solid var(--border)', borderRadius: '6px', padding: '0.75rem 1rem', marginBottom: '0.5rem' }}>
                  <legend style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <input
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...intentSettings.enabled_intents, meta.id]
                          : intentSettings.enabled_intents.filter((i) => i !== meta.id);
                        setIntentSettings({ ...intentSettings, enabled_intents: next });
                      }}
                    />
                    <strong>{meta.label}</strong>
                    <code style={{ fontSize: '0.75rem', opacity: 0.7 }}>{meta.id}</code>
                  </legend>
                  <p className="hint" style={{ margin: '0.25rem 0 0.5rem' }}>{meta.description}</p>
                  {enabled && (
                    <label style={{ display: 'block' }}>
                      <span style={{ fontSize: '0.8rem' }}>Keywords personalizadas (comma-separated)</span>
                      <input
                        type="text"
                        placeholder="ej: reservar, quiero hora"
                        value={kws}
                        onChange={(e) => {
                          const list = e.target.value.split(',').map((k) => k.trim()).filter(Boolean);
                          setIntentSettings({
                            ...intentSettings,
                            custom_keywords: { ...intentSettings.custom_keywords, [meta.id]: list },
                          });
                        }}
                        style={{ width: '100%', marginTop: '0.25rem' }}
                      />
                    </label>
                  )}
                </fieldset>
              );
            })}
          </div>

          <div className="form-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
              Guardar intenciones
            </button>
          </div>
        </form>
      ) : null}

      {activeTab === 'notificaciones' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
          <p className="hint wide" style={{ marginBottom: '0.5rem' }}>
            Configura qué recordatorios y mensajes post-cita se envían por WhatsApp.
            Cada notificación requiere una plantilla aprobada con el mismo propósito en
            la pestaña <em>Plantillas de mensajes</em> del módulo WhatsApp.
          </p>

          <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
            <legend>Confirmación y recordatorios (TASK-0035)</legend>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.confirmation_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, confirmation_enabled: e.target.checked })}
              />
              Enviar confirmación inmediata al crear la cita
            </label>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.reminder_24h_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, reminder_24h_enabled: e.target.checked })}
              />
              Recordatorio 24 horas antes
            </label>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.reminder_1h_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, reminder_1h_enabled: e.target.checked })}
              />
              Recordatorio 1 hora antes
            </label>
          </fieldset>

          <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
            <legend>Ubicación e instrucciones</legend>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.include_location_link}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, include_location_link: e.target.checked })}
              />
              Incluir ubicación en los mensajes
            </label>
            <label className="wide">
              Dirección
              <input
                value={notificationSettings.location_address}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, location_address: e.target.value })}
                placeholder="Cra. 7 #45-23, Bogotá"
              />
            </label>
            <label className="wide">
              URL de Google Maps
              <input
                value={notificationSettings.location_maps_url}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, location_maps_url: e.target.value })}
                placeholder="https://maps.google.com/?q=..."
              />
            </label>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.include_preparation_notes}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, include_preparation_notes: e.target.checked })}
              />
              Incluir instrucciones de preparación del servicio
            </label>
          </fieldset>

          <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
            <legend>Reducción de no-show (TASK-0036)</legend>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.no_show_confirmation_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, no_show_confirmation_enabled: e.target.checked })}
              />
              Enviar confirmación activa antes de la cita
            </label>
            <label>
              Horas antes de la cita
              <input
                type="number"
                min="1"
                max="48"
                value={notificationSettings.confirmation_reminder_hours}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, confirmation_reminder_hours: Number(e.target.value) || 0 })}
              />
            </label>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.auto_rebook_on_decline !== false}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, auto_rebook_on_decline: e.target.checked })}
              />
              Ofrecer reprogramar al declinar la confirmación (TASK-0044)
            </label>
            <p className="hint" style={{ marginTop: '0.25rem' }}>
              Si el cliente responde "no" al pedido de confirmación activa, el bot ofrecerá tres
              horarios alternativos en lugar de quedarse esperando a un agente. Si responde "no"
              al rebooking, la cita se cancela y se escala al equipo.
            </p>
            <label className="inline-check wide" data-wizard-field="ask_referrer">
              <input
                type="checkbox"
                checked={notificationSettings.ask_referrer === true}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, ask_referrer: e.target.checked })}
              />
              Preguntar "¿quién te recomendó?" al iniciar el booking (TASK-0055)
            </label>
            <p className="hint" style={{ marginTop: '0.25rem' }}>
              Captura al embajador para medir referidos en Analítica → Top
              referidores. Default desactivado.
            </p>
          </fieldset>

          <fieldset className="wide" style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '0.75rem 1rem' }}>
            <legend>Flujo post-cita (TASK-0036)</legend>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.post_instructions_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_instructions_enabled: e.target.checked })}
              />
              Enviar instrucciones post-servicio
            </label>
            <label>
              Minutos después del final
              <input
                type="number"
                min="0"
                max="1440"
                value={notificationSettings.post_instructions_delay_minutes}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_instructions_delay_minutes: Number(e.target.value) || 0 })}
              />
            </label>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.post_feedback_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_feedback_enabled: e.target.checked })}
              />
              Pedir feedback al cliente (1–5)
            </label>
            <label>
              Horas después del final
              <input
                type="number"
                min="0"
                max="168"
                value={notificationSettings.post_feedback_delay_hours}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_feedback_delay_hours: Number(e.target.value) || 0 })}
              />
            </label>
            <label className="inline-check wide">
              <input
                type="checkbox"
                checked={notificationSettings.post_rebooking_enabled}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_rebooking_enabled: e.target.checked })}
              />
              Invitar a nueva cita
            </label>
            <label>
              Días después
              <input
                type="number"
                min="1"
                max="365"
                value={notificationSettings.post_rebooking_delay_days}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_rebooking_delay_days: Number(e.target.value) || 0 })}
              />
            </label>
            <label className="wide">
              Mensaje personalizado de rebooking
              <textarea
                rows={2}
                value={notificationSettings.post_rebooking_message}
                onChange={(e) => setNotificationSettings({ ...notificationSettings, post_rebooking_message: e.target.value })}
                placeholder="Hola {{1}}, ya pasó un tiempo desde tu última visita. ¿Te gustaría agendar?"
              />
            </label>
          </fieldset>

          <div className="builder-preview wide">
            <strong>Preview del mensaje de confirmación</strong>
            <pre>{`Hola {nombre},

Tu cita de {servicio} quedó agendada para el {fecha} a las {hora}` + (notificationSettings.include_location_link && notificationSettings.location_address ? `\n\n📍 ${notificationSettings.location_address}` : '') + (notificationSettings.include_location_link && notificationSettings.location_maps_url ? `\n${notificationSettings.location_maps_url}` : '') + (notificationSettings.include_preparation_notes ? '\n\n📋 Instrucciones de preparación (del catálogo del servicio).' : '')}</pre>
          </div>

          <div className="form-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
              Guardar notificaciones
            </button>
          </div>
        </form>
      ) : null}

      {activeTab === 'pagos' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSavePaymentSettings}>
          <div className="wide">
            <h3>Configuración de pagos</h3>
            <p className="hint">
              Genera links de pago para tus citas usando MercadoPago o Stripe. La API key se guarda cifrada y nunca
              se devuelve al panel. Configura el webhook del proveedor apuntando a
              <code> /v1/webhooks/payments/{paymentSettings.provider === 'none' ? '{provider}' : paymentSettings.provider}</code>.
            </p>
          </div>
          <label>
            Proveedor
            <select
              onChange={(event) => setPaymentSettings({ ...paymentSettings, provider: event.target.value })}
              value={paymentSettings.provider}
            >
              <option value="none">Sin pagos</option>
              <option value="mercadopago">MercadoPago</option>
              <option value="stripe">Stripe</option>
            </select>
          </label>
          <label>
            Moneda por defecto
            <input
              maxLength={3}
              onChange={(event) => setPaymentSettings({ ...paymentSettings, currency: event.target.value.toUpperCase() })}
              placeholder="COP"
              value={paymentSettings.currency || ''}
            />
          </label>
          <label>
            Monto por defecto (opcional)
            <input
              min="0"
              onChange={(event) => setPaymentSettings({ ...paymentSettings, default_amount: event.target.value })}
              placeholder="Ej. 50000"
              step="0.01"
              type="number"
              value={paymentSettings.default_amount ?? ''}
            />
          </label>
          <label className="wide">
            API key del proveedor
            <input
              autoComplete="off"
              disabled={paymentSettings.provider === 'none'}
              onChange={(event) => setPaymentForm({ ...paymentForm, apiKey: event.target.value })}
              placeholder={paymentSettings.api_key_configured ? '••••••• (configurada, deja vacío para conservar)' : 'Pega aquí la API key'}
              type="password"
              value={paymentForm.apiKey}
            />
          </label>
          <label className="wide">
            Webhook secret (requerido)
            <input
              autoComplete="off"
              disabled={paymentSettings.provider === 'none'}
              onChange={(event) => setPaymentForm({ ...paymentForm, webhookSecret: event.target.value })}
              placeholder={paymentSettings.webhook_secret_configured ? '••••••• (configurado, deja vacío para conservar)' : 'Pega el secret de firma del proveedor'}
              type="password"
              value={paymentForm.webhookSecret}
            />
          </label>
          <div className="wide">
            <p className="hint">
              Estado: proveedor <strong>{paymentSettings.provider}</strong> ·
              API key {paymentSettings.api_key_configured ? '✅ configurada' : '⚠️ no configurada'} ·
              Webhook secret {paymentSettings.webhook_secret_configured ? '✅ configurado' : '⚠️ requerido para validar firmas del proveedor'}.
            </p>
          </div>
          <div className="form-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
              Guardar pagos
            </button>
          </div>
        </form>
      ) : null}

      {activeTab === 'privacy' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
          <label>PII policy<select value={privacyForm.mode} onChange={(event) => setPrivacyForm({ ...privacyForm, mode: event.target.value })}><option value="strict">Strict</option><option value="balanced">Balanced</option><option value="minimal">Minimal</option></select></label>
          <label>Retención PII (días)<input min="1" value={privacyForm.retentionDays} onChange={(event) => setPrivacyForm({ ...privacyForm, retentionDays: event.target.value })} type="number" /></label>
          <label className="inline-check"><input checked={privacyForm.noTrain} onChange={(event) => setPrivacyForm({ ...privacyForm, noTrain: event.target.checked })} type="checkbox" /> no_train</label>
          <label className="inline-check"><input checked={privacyForm.redactBeforeModel} onChange={(event) => setPrivacyForm({ ...privacyForm, redactBeforeModel: event.target.checked })} type="checkbox" /> Redactar antes del modelo</label>
          <label className="inline-check"><input checked={privacyForm.logRedaction} onChange={(event) => setPrivacyForm({ ...privacyForm, logRedaction: event.target.checked })} type="checkbox" /> Redactar logs</label>
          <div className="pii-builder wide">
            <strong>Reglas PII</strong>
            {Object.entries(privacyForm.rules).map(([key, value]) => (
              <label key={key}>{key}<select value={value} onChange={(event) => setPrivacyForm({ ...privacyForm, rules: { ...privacyForm.rules, [key]: event.target.value } })}><option value="allow">Allow</option><option value="mask">Mask</option><option value="redact">Redact</option></select></label>
            ))}
          </div>
          <div className="builder-preview wide"><strong>Builder resultante</strong><pre>{formatJson({ pii_policy: settingsPayload.pii_policy, no_train: settingsPayload.no_train })}</pre></div>
          <div className="form-actions"><button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar privacidad</button></div>
        </form>
      ) : null}

      {activeTab === 'ia_rag' ? (
        <div className="wizard-panel">
          <div className="ia-rag-header">
            <h3>Configuración de IA y RAG</h3>
            <p className="hint">
              El proveedor activo se configura en las variables de entorno del servidor
              (<code>RAG_EMBEDDING_PROVIDER</code>, <code>RAG_EMBEDDING_MODEL</code>).
              Desde aquí puedes re-indexar todos los documentos activos con el proveedor en uso.
            </p>
          </div>

          <div className="ia-rag-provider-info">
            <h4>Proveedores disponibles</h4>
            {embeddingProviderOptions.map((opt) => (
              <div
                key={opt.value}
                className={`provider-card ${ragForm.provider === opt.value ? 'selected' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => handleProviderChange(opt.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleProviderChange(opt.value)}
              >
                <div className="provider-card-title">
                  <strong>{opt.label}</strong>
                  <span className={`status-badge ${opt.value === 'local_hash' ? 'trial' : 'active'}`}>
                    {opt.value === 'local_hash' ? 'Léxico (hash)' : 'Semántico (real)'}
                  </span>
                </div>
                <p className="hint">{opt.description}</p>
                <small>Modelo sugerido: <code>{opt.defaultModel}</code> · {opt.defaultDims} dims</small>
              </div>
            ))}
          </div>

          <div className="ia-rag-status">
            <h4>Estado del proveedor activo en servidor</h4>
            <p className="hint">
              El badge refleja el proveedor configurado en el servidor. Para cambiar el proveedor
              activo actualiza <code>RAG_EMBEDDING_PROVIDER</code> y <code>RAG_EMBEDDING_API_KEY</code>
              en el entorno del servidor y reinicia el servicio.
            </p>
            <div className="provider-status-badge">
              <span className="status-badge active">Semántico (real)</span>
              <span className="hint"> cuando provider ≠ local_hash</span>
              <span className="status-badge suspended" style={{ marginLeft: '0.5rem' }}>Léxico (hash)</span>
              <span className="hint"> cuando provider = local_hash</span>
            </div>
          </div>

          <form className="ia-rag-reindex form-grid" onSubmit={handleReindexAll}>
            <div className="wide">
              <h4>Re-indexar todos los documentos</h4>
              <p className="hint">
                Re-procesa todos los documentos activos y draft del tenant con el proveedor de
                embeddings configurado actualmente en el servidor. Los chunks anteriores serán
                reemplazados. La operación puede tardar según el número de documentos.
              </p>
            </div>
            <div className="form-actions wide">
              <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
                {isBusy ? 'Re-indexando…' : 'Re-indexar todos los documentos'}
              </button>
            </div>
            {reindexResult && (
              <div className="builder-preview wide">
                <strong>Resultado de re-indexación</strong>
                <pre>{JSON.stringify(reindexResult, null, 2)}</pre>
              </div>
            )}
          </form>
        </div>
      ) : null}

      {activeTab === 'audit' ? (
        <div className="wizard-panel">
          <div className="audit-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} onClick={() => refreshAuditLogs()} type="button">Refrescar auditoría</button>
          </div>
          {lastSettings ? <div className="builder-preview"><strong>Últimos settings guardados</strong><pre>{formatJson(lastSettings)}</pre></div> : null}
          <div className="audit-list">
            {auditLogs.length === 0 ? <p className="hint">Aún no hay logs cargados. Guarda settings o refresca la auditoría.</p> : null}
            {auditLogs.map((log) => (
              <article className="audit-item" key={log.id}>
                <strong>{log.action}</strong>
                <span>{log.actor_type} · {log.entity_type}</span>
                <small>{log.created_at}</small>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
