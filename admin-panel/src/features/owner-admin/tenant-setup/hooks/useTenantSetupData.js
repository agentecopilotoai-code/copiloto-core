import { useEffect, useMemo, useState } from 'react';

import {
  createTenant,
  getTenant,
  getTenantSettings,
  listAuditLogs,
  patchTenantStatus,
  reindexAllKnowledgeDocuments,
  updateTenant,
  updateTenantSettings,
  uploadTenantBrandLogo,
} from '../../../../services/coreApi.js';
import {
  DEFAULT_BOT_PERSONALITY,
  DEFAULT_NOTIFICATION_SETTINGS,
  defaultPiiRules,
  embeddingProviderOptions,
} from '../tenantSetupData.js';
import {
  cloneInitialHours,
  defaultIntentSettings,
  hydrateSettings,
  toBusinessHours,
  toEscalationPolicy,
  toPiiPolicy,
} from '../tenantSetupTransforms.js';
import { useTenantSetupSidePanels } from './useTenantSetupSidePanels.js';

export function useTenantSetupData({ session, tenant, onTenantCreated, setActiveTab }) {
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
  const [botPersonality, setBotPersonality] = useState(() => ({ ...DEFAULT_BOT_PERSONALITY }));
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
  // UI-012-FU: brand logo state — `brandLogoUrl` mirrors
  // tenant_settings.brand_logo_url so the BotPersonalityTab preview can
  // reflect the current value before/after upload + "Quitar logo".
  const [brandLogoUrl, setBrandLogoUrl] = useState(null);

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
      bot_personality: botPersonality,
    }),
    [botPersonality, escalationForm, hoursForm, intentSettings, notificationSettings, privacyForm, settingsForm.locale],
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
        setBotPersonality(hydrated.botPersonality);
        setLastSettings(loadedSettings);
        setBrandLogoUrl(loadedSettings?.brand_logo_url || null);
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

  const sidePanels = useTenantSetupSidePanels({ session, currentTenantId, runAction, setNotice });

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

  // UI-012-FU: upload a logo file and reflect the new URL locally.
  async function handleUploadBrandLogo(file) {
    if (!currentTenantId || !file) return null;
    const updated = await runAction(
      () => uploadTenantBrandLogo(session, currentTenantId, file),
      'Logo de marca actualizado y auditado.',
    );
    if (updated) {
      setBrandLogoUrl(updated.brand_logo_url || null);
      setLastSettings(updated);
    }
    return updated;
  }

  // UI-012-FU: clear the logo by PATCH-ing brand_logo_url to ''
  // (the backend coerces empty string -> null).
  async function handleClearBrandLogo() {
    if (!currentTenantId) return null;
    const updated = await runAction(
      () => updateTenantSettings(session, currentTenantId, { brand_logo_url: '' }),
      'Logo de marca eliminado.',
    );
    if (updated) {
      setBrandLogoUrl(updated.brand_logo_url || null);
      setLastSettings(updated);
    }
    return updated;
  }

  async function refreshAuditLogs(tenantId = currentTenantId, showNotice = true) {
    if (!tenantId) return;
    const logs = await runAction(
      () => listAuditLogs(session, tenantId),
      showNotice ? 'Auditoría actualizada.' : 'Settings guardados y auditados.',
    );
    if (logs) setAuditLogs(logs);
  }

  return {
    state: {
      currentTenantId,
      tenantForm,
      settingsForm,
      hoursForm,
      escalationForm,
      intentSettings,
      notificationSettings,
      botPersonality,
      privacyForm,
      auditLogs,
      lastSettings,
      notice,
      isBusy,
      tenantStatus,
      statusReason,
      targetStatus,
      ragForm,
      reindexResult,
      settingsPayload,
      brandLogoUrl,
      ...sidePanels.state,
    },
    actions: {
      setTenantForm,
      setSettingsForm,
      setHoursForm,
      setEscalationForm,
      setIntentSettings,
      setNotificationSettings,
      setBotPersonality,
      setPrivacyForm,
      setNotice,
      setStatusReason,
      setTargetStatus,
      runAction,
      handleSaveTenant,
      handleSaveSettings,
      handleChangeStatus,
      handleProviderChange,
      handleReindexAll,
      handleUploadBrandLogo,
      handleClearBrandLogo,
      refreshAuditLogs,
      ...sidePanels.actions,
    },
  };
}
