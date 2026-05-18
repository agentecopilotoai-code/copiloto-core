import { useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createContactSegment,
  deleteContactSegment,
  listContactSegments,
  previewContactSegment,
  refreshContactSegment,
  updateContactSegment,
} from '../../../../services/coreApi.js';
import {
  addRule,
  buildPayload,
  emptySegmentForm,
  formFromSegment,
  parseListValue,
  removeRule,
  replaceRule,
  updateRuleField,
  updateRuleOp,
  updateRuleValue,
} from '../segmentsData.js';

/**
 * Data layer for the Manager · Segmentos view. Owns the segment list, the
 * selection, the create/edit form (including the dynamic rule array), the
 * preview state and every mutation handler extracted verbatim from the legacy
 * `SegmentsModule` (load/refresh list, create, update, delete, preview,
 * refresh-segment — including the native delete confirm). Returns
 * `{ state, actions }`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useSegmentsData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [segments, setSegments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  // BUG-039: editingId trackea la fila que se está editando, no selectedId.
  // El botón "Editar" funciona sobre cualquier fila — sin esto, submit
  // pisaba la fila seleccionada en vez de la editada.
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formMode, setFormMode] = useState('create');
  const [form, setForm] = useState(emptySegmentForm);
  const [preview, setPreview] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);

  const selectedSegment = useMemo(
    () => segments.find((s) => s.id === selectedId) || null,
    [segments, selectedId],
  );

  function refreshSegments() {
    if (!tenantId) return Promise.resolve();
    return listContactSegments(session, tenantId)
      .then((items) => {
        setSegments(items || []);
        if (items?.length && !items.some((s) => s.id === selectedId)) {
          setSelectedId(items[0].id);
        } else if (!items?.length) {
          setSelectedId(null);
        }
      })
      .catch((error) => setNotice({ type: 'error', text: error.message }));
  }

  useEffect(() => {
    if (!tenantId) return;
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
      setEditingId(null);  // BUG-039.
    },
    startCreate() {
      setFormMode('create');
      setForm(emptySegmentForm());
      setEditingId(null);  // BUG-039.
      setPreview(null);
      setShowForm(true);
    },
    startEdit(segment) {
      if (!segment) return;
      setFormMode('edit');
      setForm(formFromSegment(segment));
      setEditingId(segment.id);  // BUG-039: trackear el id real editado.
      setPreview(null);
      setShowForm(true);
    },
    // ── rule-builder handlers ──────────────────────────────────────────────
    addRule() {
      setForm((prev) => ({ ...prev, items: addRule(prev.items) }));
    },
    removeRule(index) {
      setForm((prev) => ({ ...prev, items: removeRule(prev.items, index) }));
    },
    changeRuleField(index, field) {
      setForm((prev) => ({
        ...prev,
        items: replaceRule(prev.items, index, updateRuleField(prev.items[index], field)),
      }));
    },
    changeRuleOp(index, op) {
      setForm((prev) => ({
        ...prev,
        items: replaceRule(prev.items, index, updateRuleOp(prev.items[index], op)),
      }));
    },
    changeRuleValue(index, rawValue) {
      setForm((prev) => ({
        ...prev,
        items: replaceRule(prev.items, index, updateRuleValue(prev.items[index], rawValue)),
      }));
    },
    blurRuleListValue(index, rawValue) {
      setForm((prev) => ({
        ...prev,
        items: replaceRule(prev.items, index, parseListValue(prev.items[index], rawValue)),
      }));
    },
    // ── mutations ──────────────────────────────────────────────────────────
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
          saved = await createContactSegment(session, tenantId, payload);
        } else {
          // BUG-039: usar editingId, no selectedId.
          saved = await updateContactSegment(session, tenantId, editingId, payload);
        }
        setNotice({ type: 'success', text: 'Segmento guardado.' });
        await refreshSegments();
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
        const data = await previewContactSegment(session, tenantId, selectedId, { limit: 25 });
        setPreview(data);
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async refresh() {
      if (!selectedId) return;
      setIsBusy(true);
      try {
        await refreshContactSegment(session, tenantId, selectedId);
        setNotice({ type: 'success', text: 'Segmento recalculado.' });
        await refreshSegments();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async remove() {
      if (!selectedId || !selectedSegment) return;
      if (selectedSegment.is_system) {
        setNotice({ type: 'error', text: 'Los segmentos del sistema no se eliminan.' });
        return;
      }
      const ok = await confirm({
        title: 'Eliminar segmento',
        body: `¿Eliminar el segmento "${selectedSegment.name}"?`,
        danger: true,
      });
      if (!ok) return;
      setIsBusy(true);
      try {
        await deleteContactSegment(session, tenantId, selectedId);
        setSelectedId(null);
        setPreview(null);
        await refreshSegments();
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
      segments,
      selectedId,
      selectedSegment,
      showForm,
      formMode,
      form,
      preview,
      notice,
      isBusy,
    },
    actions,
  };
}
