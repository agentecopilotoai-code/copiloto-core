import { useEffect, useMemo, useState } from 'react';

import {
  createWhatsappTemplate,
  deleteWhatsappTemplate,
  getWhatsAppChannelHealth,
  listWhatsappTemplates,
  syncWhatsappTemplates,
  upsertWhatsAppChannel,
} from '../../../services/coreApi.js';

const TEMPLATE_PURPOSES = [
  { id: 'appointment_confirmation', label: 'Confirmación de cita', required: true },
  { id: 'appointment_reminder_24h', label: 'Recordatorio 24 h', required: true },
  { id: 'appointment_reminder_1h', label: 'Recordatorio 1 h' },
  { id: 'appointment_reminder_custom', label: 'Recordatorio personalizado' },
  { id: 'no_show_confirmation_request', label: 'Pedido de confirmación (no-show)' },
  { id: 'no_show_followup', label: 'Seguimiento no-show' },
  { id: 'post_appointment_instructions', label: 'Instrucciones post-cita' },
  { id: 'post_appointment_feedback', label: 'Feedback post-cita' },
  { id: 'post_appointment_rebooking', label: 'Invitación a nueva cita' },
  { id: 'reschedule_offer', label: 'Oferta de reagendamiento' },
  { id: 'campaign_promo', label: 'Campaña / promoción' },
  { id: 'payment_request', label: 'Solicitud de pago' },
  { id: 'custom', label: 'Personalizado' },
];

const TEMPLATE_STATUS_LABEL = {
  draft: 'Borrador',
  pending: 'Pendiente',
  approved: 'Aprobado',
  rejected: 'Rechazado',
  paused: 'Pausado',
};

function emptyTemplateForm() {
  return {
    name: '',
    locale: 'es',
    category: 'utility',
    purpose: 'appointment_confirmation',
    header: '',
    body: '',
    footer: '',
    buttons: '',
  };
}

function templateComponentsFromForm(form) {
  const components = {};
  if (form.header.trim()) {
    components.header = { type: 'text', text: form.header.trim() };
  }
  if (form.body.trim()) {
    components.body = { text: form.body.trim() };
  }
  if (form.footer.trim()) {
    components.footer = { text: form.footer.trim() };
  }
  const buttons = form.buttons
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((text) => ({ type: 'QUICK_REPLY', text }));
  if (buttons.length) {
    components.buttons = buttons;
  }
  return components;
}

const onboardingSteps = [
  {
    id: 'business',
    label: 'Business Manager conectado',
    description: 'Registra el Business ID de Meta que administra el portafolio de WhatsApp.',
  },
  {
    id: 'waba',
    label: 'WABA identificado',
    description: 'Asocia el WhatsApp Business Account ID del tenant.',
  },
  {
    id: 'phone',
    label: 'Phone Number ID listo',
    description: 'Configura el número que recibirá webhooks y enviará mensajes.',
  },
  {
    id: 'secrets',
    label: 'Secretos del tenant guardados',
    description: 'Pega los tres secretos del canal; CopilotoIA los guarda en la estructura fija del tenant.',
  },
  {
    id: 'health',
    label: 'Health check validado',
    description: 'Confirma que el canal está activo en CopilotoIA y listo para pruebas controladas.',
  },
];

function defaultFormForTenant() {
  return {
    business_id: '',
    waba_id: '',
    phone_number_id: '',
    account_mode: 'mock',
    meta_access_token: '',
    app_secret: '',
    verify_token: '',
  };
}

function hasValue(value) {
  return Boolean(String(value || '').trim());
}

function channelFromHealth(health) {
  return health?.channel || null;
}

export function WhatsAppOnboarding({ module, session, tenant }) {
  const [form, setForm] = useState(() => defaultFormForTenant());
  const [health, setHealth] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLoadingChannel, setIsLoadingChannel] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [templateForm, setTemplateForm] = useState(emptyTemplateForm);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  const currentTenantId = tenant?.id;

  function loadTemplates() {
    if (!currentTenantId) return;
    setIsLoadingTemplates(true);
    listWhatsappTemplates(session, currentTenantId)
      .then((items) => setTemplates(Array.isArray(items) ? items : []))
      .catch(() => {})
      .finally(() => setIsLoadingTemplates(false));
  }

  useEffect(() => {
    setTemplates([]);
    setTemplateForm(emptyTemplateForm());
    loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTenantId]);

  async function handleCreateTemplate(event) {
    event.preventDefault();
    if (!currentTenantId) return;
    if (!templateForm.name.trim() || !templateForm.body.trim()) {
      setNotice({ type: 'error', text: 'Nombre y body son obligatorios.' });
      return;
    }
    if (!/^[a-z0-9_]+$/.test(templateForm.name.trim())) {
      setNotice({ type: 'error', text: 'El nombre debe ser snake_case (a-z, 0-9, _).' });
      return;
    }
    setIsBusy(true);
    setNotice(null);
    try {
      await createWhatsappTemplate(session, currentTenantId, {
        name: templateForm.name.trim(),
        locale: templateForm.locale.trim() || 'es',
        category: templateForm.category,
        purpose: templateForm.purpose,
        components: templateComponentsFromForm(templateForm),
      });
      setTemplateForm(emptyTemplateForm());
      loadTemplates();
      setNotice({ type: 'success', text: 'Plantilla registrada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSyncTemplates() {
    if (!currentTenantId) return;
    setIsBusy(true);
    setNotice(null);
    try {
      const result = await syncWhatsappTemplates(session, currentTenantId);
      loadTemplates();
      setNotice({
        type: 'success',
        text: `Sincronizadas ${result.updated} de ${result.meta_total} plantillas desde Meta.`,
      });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDeleteTemplate(template) {
    if (!currentTenantId) return;
    if (!window.confirm(`¿Eliminar la plantilla "${template.name}" (${template.locale})?`)) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await deleteWhatsappTemplate(session, currentTenantId, template.id);
      loadTemplates();
      setNotice({ type: 'success', text: 'Plantilla eliminada.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  const templatesByPurpose = useMemo(() => {
    const map = {};
    templates.forEach((template) => {
      const list = map[template.purpose] || [];
      list.push(template);
      map[template.purpose] = list;
    });
    return map;
  }, [templates]);
  const channel = channelFromHealth(health);

  const checklist = useMemo(() => {
    const hasSecrets = (
      health?.checks?.meta_access_token_configured
      && health?.checks?.app_secret_configured
      && health?.checks?.verify_token_configured
    ) || (hasValue(form.meta_access_token) && hasValue(form.app_secret) && hasValue(form.verify_token));
    const healthOk = channel?.status === 'active' && health?.status === 'healthy';

    return onboardingSteps.map((step) => {
      const done = {
        business: hasValue(form.business_id),
        waba: hasValue(form.waba_id),
        phone: hasValue(form.phone_number_id),
        secrets: hasSecrets,
        health: healthOk,
      }[step.id];
      return { ...step, done };
    });
  }, [channel?.status, form, health]);

  useEffect(() => {
    let mounted = true;

    setHealth(null);
    setNotice(null);
    setLoadError(null);
    setIsLoadingChannel(false);
    setForm(defaultFormForTenant());

    if (!currentTenantId) return undefined;

    setIsLoadingChannel(true);

    getWhatsAppChannelHealth(session, currentTenantId)
      .then((loadedHealth) => {
        if (!mounted) return;
        setHealth(loadedHealth);
        const loadedChannel = channelFromHealth(loadedHealth);
        if (loadedChannel) {
          setForm({
            business_id: loadedChannel.business_id || '',
            waba_id: loadedChannel.waba_id || '',
            phone_number_id: loadedChannel.phone_number_id || '',
            account_mode: loadedChannel.account_mode || defaultFormForTenant().account_mode,
            meta_access_token: '',
            app_secret: '',
            verify_token: '',
          });
        }
      })
      .catch((error) => {
        if (!mounted || error.status === 404) return;
        setLoadError(error);
        setNotice({
          type: 'error',
          text: `No se pudo cargar el canal WhatsApp existente: ${error.message}. Refresca el health antes de guardar para evitar sobrescribir referencias existentes.`,
        });
      })
      .finally(() => {
        if (mounted) setIsLoadingChannel(false);
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

  async function refreshHealth(showNotice = true) {
    if (!currentTenantId) return null;
    setIsBusy(true);
    setNotice(null);
    try {
      const loadedHealth = await getWhatsAppChannelHealth(session, currentTenantId);
      setHealth(loadedHealth);
      setLoadError(null);
      setNotice({
        type: 'success',
        text: showNotice ? 'Health check de WhatsApp actualizado.' : 'Canal WhatsApp registrado.',
      });
      return loadedHealth;
    } catch (error) {
      if (error.status === 404) {
        setHealth(null);
        setLoadError(null);
        if (showNotice) {
          setNotice({
            type: 'success',
            text: 'No hay canal WhatsApp registrado todavía; puedes completar el formulario.',
          });
        }
        return null;
      }
      setNotice({ type: 'error', text: error.message });
      return null;
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!currentTenantId) {
      setNotice({ type: 'error', text: 'Selecciona o crea un tenant antes de registrar WhatsApp.' });
      return;
    }
    if (isLoadingChannel) {
      setNotice({ type: 'error', text: 'Espera a que termine la carga del canal antes de guardar.' });
      return;
    }
    if (loadError) {
      setNotice({
        type: 'error',
        text: 'No se puede guardar hasta recuperar el canal existente o cambiar de tenant. Usa Ver health para reintentar.',
      });
      return;
    }

    const payload = { ...form };
    if (!payload.meta_access_token) delete payload.meta_access_token;
    if (!payload.app_secret) delete payload.app_secret;
    if (!payload.verify_token) delete payload.verify_token;

    const savedChannel = await runAction(
      () => upsertWhatsAppChannel(session, currentTenantId, payload),
      'Canal WhatsApp registrado. Ejecutando health check local…',
    );
    if (savedChannel) {
      await refreshHealth(false);
      setForm((currentForm) => ({ ...currentForm, meta_access_token: '', app_secret: '', verify_token: '' }));
    }
  }

  function updateField(field, value) {
    setForm((currentForm) => ({ ...currentForm, [field]: value }));
  }

  return (
    <section className="module-card wizard-card">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Onboarding WABA</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        <div className="wizard-selected-tenant">
          <span>Tenant activo</span>
          <strong>{tenant?.label || 'Sin tenant seleccionado'}</strong>
        </div>
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}
      {health?.checks?.delivery_ready === false ? (
        <p className="notice error">
          El canal está en modo real, pero el secreto meta_access_token del tenant falta o no es real.
          Pega el Meta access token, el App Secret y el Verify token en este formulario, guarda el canal y reinicia el worker antes de esperar mensajes en WhatsApp.
        </p>
      ) : null}
      {isLoadingChannel ? <p className="notice info">Cargando canal WhatsApp existente…</p> : null}

      <div className="onboarding-layout">
        <form className="wizard-panel form-grid" onSubmit={handleSubmit}>
          <label>
            Business ID
            <input
              autoComplete="off"
              onChange={(event) => updateField('business_id', event.target.value)}
              placeholder="123456789012345"
              required
              value={form.business_id}
            />
          </label>
          <label>
            WABA ID
            <input
              autoComplete="off"
              onChange={(event) => updateField('waba_id', event.target.value)}
              placeholder="987654321098765"
              required
              value={form.waba_id}
            />
          </label>
          <label>
            Phone Number ID
            <input
              autoComplete="off"
              onChange={(event) => updateField('phone_number_id', event.target.value)}
              placeholder="112233445566778"
              required
              value={form.phone_number_id}
            />
          </label>
          <label>
            Modo de entrega
            <select
              onChange={(event) => updateField('account_mode', event.target.value)}
              value={form.account_mode}
            >
              <option value="mock">Mock local (no envía a WhatsApp)</option>
              <option value="live">Real vía WhatsApp Cloud API</option>
            </select>
          </label>
          <label className="wide">
            Meta access token del tenant
            <input
              autoComplete="off"
              onChange={(event) => updateField('meta_access_token', event.target.value)}
              placeholder="Pega aquí el token real solo para guardarlo en el secreto del tenant"
              type="password"
              required={!health?.checks?.meta_access_token_configured}
              value={form.meta_access_token}
            />
            <small>Requerido la primera vez o cuando quieras rotarlo; se guarda en secrets/tenants/&lt;tenant_id&gt;/meta_access_token.</small>
          </label>
          <label className="wide">
            App secret del tenant
            <input
              autoComplete="off"
              onChange={(event) => updateField('app_secret', event.target.value)}
              placeholder="App Secret o APP_ID|APP_SECRET; CopilotoIA guardará solo el secret"
              type="password"
              required={!health?.checks?.app_secret_configured}
              value={form.app_secret}
            />
            <small>Requerido la primera vez o cuando quieras rotarlo; se guarda en secrets/tenants/&lt;tenant_id&gt;/whatsapp_app_secret. Si pegas APP_ID|APP_SECRET, se almacena solo APP_SECRET.</small>
          </label>
          <label className="wide">
            Verify token del webhook
            <input
              autoComplete="off"
              onChange={(event) => updateField('verify_token', event.target.value)}
              placeholder="Pega aquí el token de verificación que configurarás en Meta Webhooks"
              required={!health?.checks?.verify_token_configured}
              type="password"
              value={form.verify_token}
            />
            <small>Requerido la primera vez o cuando quieras rotarlo; se guarda en secrets/tenants/&lt;tenant_id&gt;/whatsapp_verify_token y el GET del webhook solo lee desde ahí.</small>
          </label>
          <div className="form-actions split-actions">
            <button
              className="secondary-action"
              disabled={isBusy || isLoadingChannel || !currentTenantId}
              onClick={() => refreshHealth()}
              type="button"
            >
              Ver health
            </button>
            <button
              className="primary-action"
              disabled={isBusy || isLoadingChannel || Boolean(loadError) || !currentTenantId}
              type="submit"
            >
              Registrar canal
            </button>
          </div>
        </form>

        <aside className="onboarding-sidebar">
          <h3>Checklist de onboarding</h3>
          <ol className="checklist">
            {checklist.map((step) => (
              <li className={step.done ? 'done' : ''} key={step.id}>
                <span aria-hidden="true">{step.done ? '✓' : '•'}</span>
                <div>
                  <strong>{step.label}</strong>
                  <small>{step.description}</small>
                </div>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      <div className="context-grid health-grid">
        <div>
          <dt>Estado local</dt>
          <dd>{health?.status || 'Sin health check'}</dd>
        </div>
        <div>
          <dt>Proveedor</dt>
          <dd>{channel?.provider || 'whatsapp_cloud_api'}</dd>
        </div>
        <div>
          <dt>Modo de entrega</dt>
          <dd>{channel?.account_mode === 'live' ? 'Real vía WhatsApp' : 'Mock local'}</dd>
        </div>
        <div>
          <dt>Token Meta</dt>
          <dd>{health?.checks?.meta_access_token_configured ? 'Configurado en backend' : 'Falta o es mock'}</dd>
        </div>
        <div>
          <dt>App Secret</dt>
          <dd>{health?.checks?.app_secret_configured ? 'Configurado por tenant' : 'Falta'}</dd>
        </div>
        <div>
          <dt>Verify token</dt>
          <dd>{health?.checks?.verify_token_configured ? 'Configurado en secreto' : 'Falta'}</dd>
        </div>
        <div>
          <dt>Entrega real lista</dt>
          <dd>{health?.checks?.delivery_ready ? 'Sí' : 'No'}</dd>
        </div>
        <div>
          <dt>Calidad</dt>
          <dd>{channel?.quality_rating || 'Pendiente de sincronización Meta'}</dd>
        </div>
        <div>
          <dt>Límite de mensajería</dt>
          <dd>{channel?.messaging_limit_tier || 'Pendiente de sincronización Meta'}</dd>
        </div>
      </div>

      <div className="wizard-panel templates-panel">
        <div className="templates-header">
          <h3>Plantillas de mensajes</h3>
          <p className="hint">
            Las plantillas aprobadas por Meta son obligatorias para enviar mensajes fuera
            de la ventana de 24 h. Configura al menos confirmación de cita y recordatorio 24 h
            antes de salir a producción.
          </p>
          <button
            className="secondary-action"
            disabled={isBusy || !currentTenantId}
            onClick={handleSyncTemplates}
            type="button"
          >
            Sincronizar estado con Meta
          </button>
        </div>

        <div className="templates-semaphore">
          {TEMPLATE_PURPOSES.filter((p) => p.required).map((purpose) => {
            const items = templatesByPurpose[purpose.id] || [];
            const approved = items.find((t) => t.status === 'approved');
            const pending = items.find((t) => t.status === 'pending');
            let semaphore = 'red';
            let label = 'Faltante';
            if (approved) {
              semaphore = 'green';
              label = 'Aprobada';
            } else if (pending) {
              semaphore = 'yellow';
              label = 'Pendiente';
            }
            return (
              <div className={`semaphore-card semaphore-${semaphore}`} key={purpose.id}>
                <strong>{purpose.label}</strong>
                <span>{label}</span>
              </div>
            );
          })}
        </div>

        <form className="form-grid" onSubmit={handleCreateTemplate}>
          <label>
            Nombre (snake_case)
            <input
              maxLength={512}
              onChange={(event) => setTemplateForm({ ...templateForm, name: event.target.value })}
              placeholder="appointment_confirmation_es"
              value={templateForm.name}
            />
          </label>
          <label>
            Idioma
            <input
              maxLength={5}
              onChange={(event) => setTemplateForm({ ...templateForm, locale: event.target.value })}
              placeholder="es"
              value={templateForm.locale}
            />
          </label>
          <label>
            Categoría
            <select
              onChange={(event) => setTemplateForm({ ...templateForm, category: event.target.value })}
              value={templateForm.category}
            >
              <option value="utility">utility</option>
              <option value="marketing">marketing</option>
              <option value="authentication">authentication</option>
            </select>
          </label>
          <label>
            Propósito
            <select
              onChange={(event) => setTemplateForm({ ...templateForm, purpose: event.target.value })}
              value={templateForm.purpose}
            >
              {TEMPLATE_PURPOSES.map((purpose) => (
                <option key={purpose.id} value={purpose.id}>{purpose.label}</option>
              ))}
            </select>
          </label>
          <label className="wide">
            Header (texto opcional)
            <input
              onChange={(event) => setTemplateForm({ ...templateForm, header: event.target.value })}
              placeholder="Recordatorio de cita"
              value={templateForm.header}
            />
          </label>
          <label className="wide">
            Body (usa variables {`{{1}}, {{2}}…`})
            <textarea
              onChange={(event) => setTemplateForm({ ...templateForm, body: event.target.value })}
              placeholder="Hola {{1}}, te recordamos tu cita el {{2}} a las {{3}}."
              rows={3}
              value={templateForm.body}
            />
          </label>
          <label className="wide">
            Footer (opcional)
            <input
              onChange={(event) => setTemplateForm({ ...templateForm, footer: event.target.value })}
              placeholder="Equipo de soporte"
              value={templateForm.footer}
            />
          </label>
          <label className="wide">
            Botones (uno por línea, opcional)
            <textarea
              onChange={(event) => setTemplateForm({ ...templateForm, buttons: event.target.value })}
              placeholder="Confirmar&#10;Reagendar"
              rows={2}
              value={templateForm.buttons}
            />
          </label>
          <div className="form-actions">
            <button className="primary-action" disabled={isBusy || !currentTenantId} type="submit">
              Registrar plantilla
            </button>
          </div>
        </form>

        <div className="templates-list">
          {isLoadingTemplates ? <p className="hint">Cargando plantillas…</p> : null}
          {templates.length === 0 && !isLoadingTemplates ? (
            <p className="hint">Aún no hay plantillas registradas.</p>
          ) : null}
          {templates.map((template) => (
            <article className="template-row" key={template.id}>
              <div>
                <strong>{template.name}</strong> · <code>{template.locale}</code>
                <div className="hint">
                  {TEMPLATE_PURPOSES.find((p) => p.id === template.purpose)?.label || template.purpose}
                  {' · '}categoría {template.category}
                </div>
                {template.rejection_reason ? (
                  <p className="notice error">{template.rejection_reason}</p>
                ) : null}
              </div>
              <div className="template-actions">
                <span className={`status-badge template-status-${template.status}`}>
                  {TEMPLATE_STATUS_LABEL[template.status] || template.status}
                </span>
                <button
                  className="secondary-action"
                  disabled={isBusy}
                  onClick={() => handleDeleteTemplate(template)}
                  type="button"
                >
                  Eliminar
                </button>
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className="builder-preview">
        <strong>Variables y secretos requeridos</strong>
        <pre>{`Meta access token: CopilotoIA lo escribe en secrets/tenants/<tenant_id>/meta_access_token para envíos outbound.
App Secret: CopilotoIA lo escribe en secrets/tenants/<tenant_id>/whatsapp_app_secret para validar X-Hub-Signature-256; si pegas APP_ID|APP_SECRET, se usa solo la parte APP_SECRET.
Verify token: CopilotoIA lo escribe en secrets/tenants/<tenant_id>/whatsapp_verify_token y el GET del webhook lo compara solo contra ese secreto.
Modo mock: el worker marca el mensaje como simulado y no llama a Meta.
Modo real: el worker llama a Meta usando el secreto meta_access_token del tenant; si ese secreto falta o es local-mock/change-me, el mensaje falla explícitamente.
El usuario solo pega los tres valores secretos; las referencias internas se derivan automáticamente con la misma estructura para todos los tenants.`}</pre>
      </div>
    </section>
  );
}
