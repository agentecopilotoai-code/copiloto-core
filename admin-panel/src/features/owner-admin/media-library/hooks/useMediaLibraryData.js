import { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createPromotion,
  deleteMediaAsset,
  deletePromotion,
  listMediaAssets,
  listPromotions,
  listServices,
  updateMediaAsset,
  updatePromotion,
  uploadMediaAsset,
} from '../../../../services/coreApi.js';
import {
  buildPromoPayload,
  emptyPromoForm,
  emptyUploadForm,
  labelFromFileName,
  parseTags,
  promoFormFromPromotion,
  validateUploadFile,
} from '../mediaLibraryData.js';

/**
 * Data layer for the IA · Medios y promociones view. Owns the media assets, the
 * promotions, the services lookup, the upload form and the promotion form, plus
 * every mutation handler extracted verbatim from the legacy `MediaLibraryModule`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useMediaLibraryData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [assets, setAssets] = useState([]);
  const [promotions, setPromotions] = useState([]);
  const [services, setServices] = useState([]);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const [uploadForm, setUploadForm] = useState(emptyUploadForm);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [promoForm, setPromoForm] = useState(emptyPromoForm);
  const [editingPromoId, setEditingPromoId] = useState(null);
  const [promoOpen, setPromoOpen] = useState(false);

  const assetsById = useMemo(() => {
    const map = new Map();
    assets.forEach((asset) => map.set(asset.id, asset));
    return map;
  }, [assets]);

  const servicesById = useMemo(() => {
    const map = new Map();
    services.forEach((service) => map.set(service.id, service));
    return map;
  }, [services]);

  const reload = useCallback(async () => {
    if (!tenantId) return;
    setIsLoading(true);
    try {
      const [mediaList, promoList, serviceList] = await Promise.all([
        listMediaAssets(session, tenantId),
        listPromotions(session, tenantId, { includeInactive: true }),
        listServices(session, tenantId, { includeInactive: false }),
      ]);
      setAssets(mediaList || []);
      setPromotions(promoList || []);
      setServices(serviceList || []);
    } catch (error) {
      setNotice({ type: 'error', text: `No se pudo cargar la biblioteca: ${error.message}` });
    } finally {
      setIsLoading(false);
    }
  }, [session, tenantId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const actions = {
    setUploadForm,
    setPromoForm,
    dismissNotice: () => setNotice(null),
    refresh: reload,
    openUpload: () => {
      setUploadForm(emptyUploadForm());
      setUploadOpen(true);
    },
    closeUpload: () => setUploadOpen(false),
    pickFile: (file) => {
      if (!file) {
        setUploadForm((prev) => ({ ...prev, file: null }));
        return;
      }
      const { kind, error } = validateUploadFile(file);
      if (error) {
        setNotice({ type: 'error', text: error });
        // BUG-109: si el usuario ya había seleccionado un archivo válido y
        // luego selecciona uno inválido, sin esta limpieza el `uploadForm.file`
        // viejo quedaba en state y `upload()` terminaba enviando el archivo
        // anterior. Limpiamos `file` (y `kind`) para forzar al usuario a
        // elegir uno nuevo.
        setUploadForm((prev) => ({ ...prev, file: null, kind: '' }));
        return;
      }
      setUploadForm((prev) => ({
        ...prev,
        file,
        kind,
        label: prev.label || labelFromFileName(file),
      }));
    },
    openCreatePromo: () => {
      setEditingPromoId(null);
      setPromoForm(emptyPromoForm());
      setPromoOpen(true);
    },
    openEditPromo: (promo) => {
      setEditingPromoId(promo.id);
      setPromoForm(promoFormFromPromotion(promo));
      setPromoOpen(true);
    },
    closePromo: () => setPromoOpen(false),
    async upload() {
      if (!tenantId) return;
      if (!uploadForm.file) {
        setNotice({ type: 'error', text: 'Selecciona un archivo primero.' });
        return;
      }
      if (!uploadForm.label.trim()) {
        setNotice({ type: 'error', text: 'La etiqueta del archivo es obligatoria.' });
        return;
      }
      setIsBusy(true);
      try {
        await uploadMediaAsset(session, tenantId, {
          kind: uploadForm.kind,
          label: uploadForm.label.trim(),
          description: uploadForm.description.trim(),
          tags: parseTags(uploadForm.tags),
          file: uploadForm.file,
        });
        setUploadForm(emptyUploadForm());
        setUploadOpen(false);
        setNotice({ type: 'success', text: 'Medio subido correctamente.' });
        await reload();
      } catch (error) {
        setNotice({ type: 'error', text: error.message || 'Error al subir.' });
      } finally {
        setIsBusy(false);
      }
    },
    async deleteAsset(asset) {
      const ok = await confirm({
        title: 'Eliminar archivo',
        body: `¿Eliminar el archivo "${asset.label}"?`,
        danger: true,
      });
      if (!ok) return;
      setIsBusy(true);
      try {
        await deleteMediaAsset(session, tenantId, asset.id);
        setNotice({ type: 'success', text: 'Archivo eliminado.' });
        await reload();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async editAssetTags(asset) {
      // UI-011 follow-up: the backlog criterio only covers the alert/confirm
      // primitives; this `window.prompt` stays for now until a dedicated
      // TagPromptDialog primitive ships in a separate task.
      const next = window.prompt('Tags (separados por coma):', (asset.tags || []).join(', '));
      if (next == null) return;
      setIsBusy(true);
      try {
        await updateMediaAsset(session, tenantId, asset.id, { tags: parseTags(next) });
        await reload();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async submitPromo() {
      if (!tenantId) return;
      const { payload, error } = buildPromoPayload(promoForm);
      if (error) {
        setNotice({ type: 'error', text: error });
        return;
      }
      setIsBusy(true);
      try {
        if (editingPromoId) {
          await updatePromotion(session, tenantId, editingPromoId, payload);
          setNotice({ type: 'success', text: 'Promoción actualizada.' });
        } else {
          await createPromotion(session, tenantId, payload);
          setNotice({ type: 'success', text: 'Promoción creada.' });
        }
        setEditingPromoId(null);
        setPromoForm(emptyPromoForm());
        setPromoOpen(false);
        await reload();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async removePromo(promo) {
      const ok = await confirm({
        title: 'Eliminar promoción',
        body: `¿Eliminar la promoción "${promo.name}"?`,
        danger: true,
      });
      if (!ok) return;
      setIsBusy(true);
      try {
        await deletePromotion(session, tenantId, promo.id);
        setNotice({ type: 'success', text: 'Promoción eliminada.' });
        if (editingPromoId === promo.id) {
          setEditingPromoId(null);
          setPromoForm(emptyPromoForm());
          setPromoOpen(false);
        }
        await reload();
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
      assets,
      promotions,
      services,
      assetsById,
      servicesById,
      notice,
      isBusy,
      isLoading,
      uploadForm,
      uploadOpen,
      promoForm,
      editingPromoId,
      promoOpen,
    },
    actions,
  };
}
