import { useEffect, useMemo, useState } from 'react';

import { getWhatsAppChannelHealth, upsertWhatsAppChannel } from '../../../services/coreApi.js';

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
    label: 'Secretos referenciados',
    description: 'Usa referencias a secretos locales o del vault; nunca pegues tokens reales en el panel.',
  },
  {
    id: 'health',
    label: 'Health check validado',
    description: 'Confirma que el canal está activo en CopilotoIA y listo para pruebas controladas.',
  },
];

function defaultFormForTenant(tenantId) {
  const secretPrefix = tenantId ? `secrets/tenants/${tenantId}` : 'secrets';

  return {
    business_id: '',
    waba_id: '',
    phone_number_id: '',
    token_ref: `${secretPrefix}/meta_access_token`,
    app_secret_ref: `${secretPrefix}/whatsapp_app_secret`,
    account_mode: 'mock',
    meta_access_token: '',
    app_secret: '',
  };
}

function hasValue(value) {
  return Boolean(String(value || '').trim());
}

function channelFromHealth(health) {
  return health?.channel || null;
}

export function WhatsAppOnboarding({ module, session, tenant }) {
  const [form, setForm] = useState(() => defaultFormForTenant(tenant?.id));
  const [health, setHealth] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLoadingChannel, setIsLoadingChannel] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const currentTenantId = tenant?.id;
  const channel = channelFromHealth(health);

  const checklist = useMemo(() => {
    const hasSecrets = hasValue(form.token_ref) && hasValue(form.app_secret_ref);
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
  }, [channel?.status, form, health?.status]);

  useEffect(() => {
    let mounted = true;

    setHealth(null);
    setNotice(null);
    setLoadError(null);
    setIsLoadingChannel(false);
    setForm(defaultFormForTenant(currentTenantId));

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
            token_ref: loadedChannel.token_ref || defaultFormForTenant(currentTenantId).token_ref,
            app_secret_ref: loadedChannel.app_secret_ref || defaultFormForTenant(currentTenantId).app_secret_ref,
            account_mode: loadedChannel.account_mode || defaultFormForTenant(currentTenantId).account_mode,
            meta_access_token: '',
            app_secret: '',
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

    const savedChannel = await runAction(
      () => upsertWhatsAppChannel(session, currentTenantId, payload),
      'Canal WhatsApp registrado. Ejecutando health check local…',
    );
    if (savedChannel) {
      await refreshHealth(false);
      if (savedChannel.generated_verify_token) {
        setNotice({
          type: 'success',
          text: `Canal registrado. Copia este Verify token en Meta Webhooks; solo se muestra una vez: ${savedChannel.generated_verify_token}`,
        });
      }
      setForm((currentForm) => ({ ...currentForm, meta_access_token: '', app_secret: '' }));
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
          El canal está en modo real, pero token_ref no resuelve a un Meta access token real para este tenant.
          Pega el Meta access token y el App secret del tenant en este formulario, guarda el canal y reinicia el worker antes de esperar mensajes en WhatsApp.
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
            Token ref
            <input
              autoComplete="off"
              onChange={(event) => updateField('token_ref', event.target.value)}
              required
              value={form.token_ref}
            />
            <small>No pegues aquí el token real de Meta; guarda una referencia por tenant como secrets/tenants/<tenant_id>/meta_access_token.</small>
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
              value={form.meta_access_token}
            />
            <small>Requerido la primera vez o cuando quieras rotarlo; no se guarda en la base de datos.</small>
          </label>
          <label className="wide">
            App secret ref
            <input
              autoComplete="off"
              onChange={(event) => updateField('app_secret_ref', event.target.value)}
              required
              value={form.app_secret_ref}
            />
          </label>
          <label className="wide">
            App secret del tenant
            <input
              autoComplete="off"
              onChange={(event) => updateField('app_secret', event.target.value)}
              placeholder="Pega aquí el App Secret solo para guardarlo en el secreto del tenant"
              type="password"
              value={form.app_secret}
            />
            <small>Requerido la primera vez o cuando quieras rotarlo; se usa para validar firmas de webhook de este tenant.</small>
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
          <dd>{health?.checks?.verify_token_configured ? 'Generado/configurado' : 'Falta'}</dd>
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

      <div className="builder-preview">
        <strong>Variables y secretos requeridos</strong>
        <pre>{`Verify token: CopilotoIA lo genera al registrar el canal; cópialo en Meta Webhooks cuando aparezca en el aviso.
Meta access token: pégalo en el campo secreto del tenant; CopilotoIA lo escribe en ${form.token_ref}.
App Secret: pégalo en el campo secreto del tenant; CopilotoIA lo escribe en ${form.app_secret_ref}.
Modo mock: el worker marca el mensaje como simulado y no llama a Meta.
Modo real: el worker llama a Meta usando el token_ref del tenant; si ese secreto falta o es local-mock/change-me, el mensaje falla explícitamente.
El panel escribe los secretos por tenant y guarda referencias (token_ref/app_secret_ref), no valores secretos en la base de datos.`}</pre>
      </div>
    </section>
  );
}
