import { useMemo, useState } from 'react';

import { createTenant, listAuditLogs, updateTenantSettings } from '../../../services/coreApi.js';

const wizardTabs = [
  { id: 'tenant', label: 'Tenant' },
  { id: 'settings', label: 'Settings' },
  { id: 'hours', label: 'Horarios' },
  { id: 'escalation', label: 'Escalamiento' },
  { id: 'privacy', label: 'Privacidad' },
  { id: 'audit', label: 'Auditoría' },
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

const verticalOptions = [
  { value: 'field_service', label: 'Field service' },
  { value: 'beauty', label: 'Beauty' },
  { value: 'pet_grooming', label: 'Pet grooming' },
];

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

export function TenantSetupWizard({ module, onTenantCreated, session, tenant }) {
  const [activeTab, setActiveTab] = useState('tenant');
  const [tenantForm, setTenantForm] = useState({
    slug: 'tenant-demo',
    legal_name: 'Tenant Demo S.A.S.',
    display_name: 'Tenant Demo',
    vertical_code: 'field_service',
    country_code: 'CO',
    timezone: 'America/Bogota',
  });
  const [settingsForm, setSettingsForm] = useState({ locale: 'es-CO' });
  const [hoursForm, setHoursForm] = useState(initialHours);
  const [escalationForm, setEscalationForm] = useState({
    enabled: true,
    queue: 'default-support',
    priority: 'normal',
    afterBotTurns: 5,
    confidenceBelow: 0.55,
    keywords: 'humano, asesor, agente, reclamo',
    handoffMessage: 'Te conecto con una persona del equipo para ayudarte mejor.',
  });
  const [privacyForm, setPrivacyForm] = useState({
    mode: 'balanced',
    retentionDays: 180,
    redactBeforeModel: true,
    logRedaction: true,
    noTrain: true,
    maxBotTurns: 8,
    rules: defaultPiiRules,
  });
  const [auditLogs, setAuditLogs] = useState([]);
  const [lastSettings, setLastSettings] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);

  const settingsPayload = useMemo(
    () => ({
      locale: settingsForm.locale,
      business_hours: toBusinessHours(hoursForm),
      escalation_policy: toEscalationPolicy(escalationForm),
      pii_policy: toPiiPolicy(privacyForm),
      no_train: privacyForm.noTrain,
      max_bot_turns: Number(privacyForm.maxBotTurns),
    }),
    [escalationForm, hoursForm, privacyForm, settingsForm.locale],
  );

  const currentTenantId = tenant?.id;

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

  async function handleCreateTenant(event) {
    event.preventDefault();
    const created = await runAction(() => createTenant(session, tenantForm), 'Tenant creado y registrado en auditoría.');
    if (created) {
      onTenantCreated?.({ id: created.id, label: `${created.slug} · ${created.id}` });
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
        <form className="wizard-panel form-grid" onSubmit={handleCreateTenant}>
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
            Vertical
            <select value={tenantForm.vertical_code} onChange={(event) => setTenantForm({ ...tenantForm, vertical_code: event.target.value })}>
              {verticalOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
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
            <button className="primary-action" disabled={isBusy} type="submit">Crear tenant</button>
          </div>
        </form>
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

      {activeTab === 'escalation' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
          <label className="inline-check wide">
            <input checked={escalationForm.enabled} onChange={(event) => setEscalationForm({ ...escalationForm, enabled: event.target.checked })} type="checkbox" />
            Habilitar escalamiento humano
          </label>
          <label>Cola<input value={escalationForm.queue} onChange={(event) => setEscalationForm({ ...escalationForm, queue: event.target.value })} /></label>
          <label>Prioridad<select value={escalationForm.priority} onChange={(event) => setEscalationForm({ ...escalationForm, priority: event.target.value })}><option>low</option><option>normal</option><option>high</option></select></label>
          <label>Escalar después de turnos bot<input min="1" value={escalationForm.afterBotTurns} onChange={(event) => setEscalationForm({ ...escalationForm, afterBotTurns: event.target.value })} type="number" /></label>
          <label>Confianza menor a<input max="1" min="0" step="0.01" value={escalationForm.confidenceBelow} onChange={(event) => setEscalationForm({ ...escalationForm, confidenceBelow: event.target.value })} type="number" /></label>
          <label className="wide">Keywords<input value={escalationForm.keywords} onChange={(event) => setEscalationForm({ ...escalationForm, keywords: event.target.value })} /></label>
          <label className="wide">Mensaje de handoff<textarea value={escalationForm.handoffMessage} onChange={(event) => setEscalationForm({ ...escalationForm, handoffMessage: event.target.value })} /></label>
          <div className="form-actions"><button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar escalamiento</button></div>
        </form>
      ) : null}

      {activeTab === 'privacy' ? (
        <form className="wizard-panel form-grid" onSubmit={handleSaveSettings}>
          <label>PII policy<select value={privacyForm.mode} onChange={(event) => setPrivacyForm({ ...privacyForm, mode: event.target.value })}><option value="strict">Strict</option><option value="balanced">Balanced</option><option value="minimal">Minimal</option></select></label>
          <label>Retención PII (días)<input min="1" value={privacyForm.retentionDays} onChange={(event) => setPrivacyForm({ ...privacyForm, retentionDays: event.target.value })} type="number" /></label>
          <label>max_bot_turns<input min="1" max="50" value={privacyForm.maxBotTurns} onChange={(event) => setPrivacyForm({ ...privacyForm, maxBotTurns: event.target.value })} type="number" /></label>
          <label className="inline-check"><input checked={privacyForm.noTrain} onChange={(event) => setPrivacyForm({ ...privacyForm, noTrain: event.target.checked })} type="checkbox" /> no_train</label>
          <label className="inline-check"><input checked={privacyForm.redactBeforeModel} onChange={(event) => setPrivacyForm({ ...privacyForm, redactBeforeModel: event.target.checked })} type="checkbox" /> Redactar antes del modelo</label>
          <label className="inline-check"><input checked={privacyForm.logRedaction} onChange={(event) => setPrivacyForm({ ...privacyForm, logRedaction: event.target.checked })} type="checkbox" /> Redactar logs</label>
          <div className="pii-builder wide">
            <strong>Reglas PII</strong>
            {Object.entries(privacyForm.rules).map(([key, value]) => (
              <label key={key}>{key}<select value={value} onChange={(event) => setPrivacyForm({ ...privacyForm, rules: { ...privacyForm.rules, [key]: event.target.value } })}><option value="allow">Allow</option><option value="mask">Mask</option><option value="redact">Redact</option></select></label>
            ))}
          </div>
          <div className="builder-preview wide"><strong>Builder resultante</strong><pre>{formatJson({ pii_policy: settingsPayload.pii_policy, no_train: settingsPayload.no_train, max_bot_turns: settingsPayload.max_bot_turns })}</pre></div>
          <div className="form-actions"><button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">Guardar privacidad</button></div>
        </form>
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
