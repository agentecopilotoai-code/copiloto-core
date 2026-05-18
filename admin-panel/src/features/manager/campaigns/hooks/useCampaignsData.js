import { useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  cancelCampaign,
  createCampaign,
  launchCampaign,
  listCampaigns,
  listContactSegments,
  listContactTags,
  listWhatsappTemplates,
  previewCampaign,
  updateCampaign,
} from '../../../../services/coreApi.js';
import { buildPayload, emptyCampaignForm, formFromCampaign } from '../campaignsData.js';

/**
 * Data layer for the Manager · Campañas view. Owns the campaign list, the
 * selection, the templates / tags / saved segments lookups, the create/edit
 * form and the preview/delivery state, plus every mutation handler extracted
 * verbatim from the legacy `CampaignsModule` (load/refresh, create, update,
 * preview, launch, cancel — including the native launch/cancel confirms).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useCampaignsData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [campaigns, setCampaigns] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);
  const [segments, setSegments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  // BUG-038: editingId es distinto de selectedId. Editar una fila no
  // seleccionada NO debe usar selectedId en el update — usaba la id vieja
  // y pisaba la otra campaña. Reset a null en startCreate/closeForm.
  const [editingId, setEditingId] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formMode, setFormMode] = useState('create');
  const [form, setForm] = useState(emptyCampaignForm);

  const selectedCampaign = useMemo(
    () => campaigns.find((c) => c.id === selectedId) || null,
    [campaigns, selectedId],
  );

  function refreshCampaigns() {
    if (!tenantId) return Promise.resolve();
    return listCampaigns(session, tenantId)
      .then((items) => {
        setCampaigns(items || []);
        if (items?.length && !items.some((c) => c.id === selectedId)) {
          setSelectedId(items[0].id);
        } else if (!items?.length) {
          setSelectedId(null);
        }
      })
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshTemplates() {
    if (!tenantId) return Promise.resolve();
    return listWhatsappTemplates(session, tenantId, { status: 'approved' })
      .then((items) => setTemplates(items || []))
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  function refreshTags() {
    if (!tenantId) return Promise.resolve();
    return listContactTags(session, tenantId)
      .then((items) => setAvailableTags(items || []))
      .catch(() => setAvailableTags([]));
  }

  function refreshSegments() {
    if (!tenantId) return Promise.resolve();
    return listContactSegments(session, tenantId)
      .then((items) => setSegments(items || []))
      .catch(() => setSegments([]));
  }

  useEffect(() => {
    if (!tenantId) return;
    refreshCampaigns();
    refreshTemplates();
    refreshTags();
    refreshSegments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  const actions = {
    setForm,
    dismissNotice: () => setNotice(null),
    select(id) {
      setSelectedId(id);
      setShowForm(false);
      setPreview(null);
    },
    closeForm: () => {
      setShowForm(false);
      setEditingId(null);  // BUG-038: clear edit target on cancel.
    },
    startCreate() {
      setFormMode('create');
      setForm(emptyCampaignForm());
      setEditingId(null);  // BUG-038: create no debe arrastrar editingId previo.
      setPreview(null);
      setShowForm(true);
    },
    startEdit(campaign) {
      if (!campaign) return;
      setFormMode('edit');
      setForm(formFromCampaign(campaign));
      // BUG-038: trackear el id de la fila que se está editando, no
      // depender de `selectedId`. La tabla permite click en "Editar" sobre
      // CUALQUIER fila (no solo la seleccionada — el handler hace
      // event.stopPropagation), así que `selectedId` puede apuntar a una
      // fila distinta. Sin esto, `submit()` llamaba updateCampaign con el
      // `selectedId` viejo y pisaba la otra campaña con el form de ésta.
      setEditingId(campaign.id);
      setPreview(null);
      setShowForm(true);
    },
    toggleTagInForm(tagId) {
      setForm((prev) => {
        const has = prev.segment.tags.includes(tagId);
        const next = has
          ? prev.segment.tags.filter((id) => id !== tagId)
          : [...prev.segment.tags, tagId];
        return { ...prev, segment: { ...prev.segment, tags: next } };
      });
    },
    async submit() {
      const { payload, error } = buildPayload(form);
      if (error) {
        setNotice({ type: 'error', text: error });
        return;
      }
      setIsBusy(true);
      try {
        let saved;
        if (formMode === 'create') {
          saved = await createCampaign(session, tenantId, payload);
        } else {
          // BUG-038: usar editingId (id de la fila que se está editando),
          // no selectedId (id de la fila seleccionada — puede ser otra).
          saved = await updateCampaign(session, tenantId, editingId, payload);
        }
        setNotice({ type: 'success', text: 'Campaña guardada.' });
        await refreshCampaigns();
        setSelectedId(saved.id);
        setEditingId(null);
        setShowForm(false);
      } catch (err) {
        setNotice({ type: 'error', text: err.message });
      } finally {
        setIsBusy(false);
      }
    },
    async preview() {
      if (!selectedId) return;
      setIsBusy(true);
      try {
        const data = await previewCampaign(session, tenantId, selectedId);
        setPreview(data);
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async launch() {
      if (!selectedId) return;
      const ok = await confirm({
        title: 'Programar envío',
        body: '¿Programar el envío de esta campaña? El worker procesará los destinatarios.',
      });
      if (!ok) return;
      setIsBusy(true);
      try {
        const next = selectedCampaign?.scheduled_at;
        await launchCampaign(session, tenantId, selectedId, next ? { scheduled_at: next } : {});
        setNotice({ type: 'success', text: 'Campaña programada. El worker la procesará.' });
        await refreshCampaigns();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async cancel() {
      if (!selectedId) return;
      const ok = await confirm({
        title: 'Cancelar campaña',
        body: '¿Cancelar la campaña? Los destinatarios ya encolados aún se enviarán.',
        danger: true,
      });
      if (!ok) return;
      setIsBusy(true);
      try {
        await cancelCampaign(session, tenantId, selectedId);
        setNotice({ type: 'success', text: 'Campaña cancelada.' });
        await refreshCampaigns();
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
      campaigns,
      templates,
      availableTags,
      segments,
      selectedId,
      selectedCampaign,
      notice,
      isBusy,
      preview,
      showForm,
      formMode,
      form,
    },
    actions,
  };
}
