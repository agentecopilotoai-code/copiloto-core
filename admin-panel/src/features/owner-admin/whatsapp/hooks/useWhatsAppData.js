import { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createWhatsappTemplate,
  deleteWhatsappTemplate,
  getWhatsAppChannelHealth,
  listWhatsappTemplates,
  syncWhatsappTemplates,
  upsertWhatsAppChannel,
} from '../../../../services/coreApi.js';
import {
  buildChecklist,
  channelFromHealth,
  defaultFormForTenant,
  emptyTemplateForm,
  formFromChannel,
  groupTemplatesByPurpose,
  templateComponentsFromForm,
  validateTemplateForm,
} from '../whatsappData.js';

/**
 * Data layer for the Canales · WhatsApp Cloud API view. Owns the channel form,
 * the health snapshot and the message-template state, plus every mutation
 * handler extracted verbatim from the legacy `WhatsAppOnboarding`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useWhatsAppData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [form, setForm] = useState(defaultFormForTenant);
  const [health, setHealth] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLoadingChannel, setIsLoadingChannel] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [templateForm, setTemplateForm] = useState(emptyTemplateForm);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  const loadTemplates = useCallback(() => {
    if (!tenantId) return;
    setIsLoadingTemplates(true);
    listWhatsappTemplates(session, tenantId)
      .then((items) => setTemplates(Array.isArray(items) ? items : []))
      .catch(() => {})
      .finally(() => setIsLoadingTemplates(false));
  }, [session, tenantId]);

  useEffect(() => {
    setTemplates([]);
    setTemplateForm(emptyTemplateForm());
    loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    let mounted = true;
    setHealth(null);
    setNotice(null);
    setLoadError(null);
    setIsLoadingChannel(false);
    setForm(defaultFormForTenant());

    if (!tenantId) return undefined;

    setIsLoadingChannel(true);
    getWhatsAppChannelHealth(session, tenantId)
      .then((loadedHealth) => {
        if (!mounted) return;
        setHealth(loadedHealth);
        const loadedChannel = channelFromHealth(loadedHealth);
        if (loadedChannel) setForm(formFromChannel(loadedChannel));
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
  }, [tenantId, session]);

  const channel = channelFromHealth(health);
  const templatesByPurpose = useMemo(
    () => groupTemplatesByPurpose(templates),
    [templates],
  );
  const checklist = useMemo(
    () => buildChecklist(form, health, channel),
    [form, health, channel],
  );

  const refreshHealth = useCallback(
    async (showNotice = true) => {
      if (!tenantId) return null;
      setIsBusy(true);
      setNotice(null);
      try {
        const loadedHealth = await getWhatsAppChannelHealth(session, tenantId);
        setHealth(loadedHealth);
        setLoadError(null);
        setNotice({
          type: 'success',
          text: showNotice
            ? 'Health check de WhatsApp actualizado.'
            : 'Canal WhatsApp registrado.',
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
    },
    [session, tenantId],
  );

  const actions = {
    setTemplateForm,
    refreshHealth,
    dismissNotice: () => setNotice(null),
    updateField: (field, value) =>
      setForm((current) => ({ ...current, [field]: value })),
    async submitChannel() {
      if (!tenantId) {
        setNotice({
          type: 'error',
          text: 'Selecciona o crea un tenant antes de registrar WhatsApp.',
        });
        return;
      }
      if (isLoadingChannel) {
        setNotice({
          type: 'error',
          text: 'Espera a que termine la carga del canal antes de guardar.',
        });
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

      setIsBusy(true);
      setNotice(null);
      try {
        const saved = await upsertWhatsAppChannel(session, tenantId, payload);
        if (saved) {
          await refreshHealth(false);
          setForm((current) => ({
            ...current,
            meta_access_token: '',
            app_secret: '',
            verify_token: '',
          }));
        }
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async createTemplate() {
      if (!tenantId) return;
      const validationError = validateTemplateForm(templateForm);
      if (validationError) {
        setNotice({ type: 'error', text: validationError });
        return;
      }
      setIsBusy(true);
      setNotice(null);
      try {
        await createWhatsappTemplate(session, tenantId, {
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
    },
    async syncTemplates() {
      if (!tenantId) return;
      setIsBusy(true);
      setNotice(null);
      try {
        const result = await syncWhatsappTemplates(session, tenantId);
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
    },
    async deleteTemplate(template) {
      if (!tenantId) return;
      const ok = await confirm({
        title: 'Eliminar plantilla',
        body: `¿Eliminar la plantilla "${template.name}" (${template.locale})?`,
        danger: true,
      });
      if (!ok) return;
      setIsBusy(true);
      setNotice(null);
      try {
        await deleteWhatsappTemplate(session, tenantId, template.id);
        loadTemplates();
        setNotice({ type: 'success', text: 'Plantilla eliminada.' });
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
  };

  return {
    state: {
      tenantId,
      form,
      health,
      channel,
      notice,
      isBusy,
      isLoadingChannel,
      loadError,
      templates,
      templateForm,
      isLoadingTemplates,
      templatesByPurpose,
      checklist,
    },
    actions,
  };
}
