import { useCallback, useEffect, useMemo, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createKnowledgeDocument,
  deleteKnowledgeDocument,
  evaluateIntent,
  getKnowledgeStorageSettings,
  indexKnowledgeDocument,
  listKnowledgeDocuments,
  updateKnowledgeDocument,
  uploadKnowledgeDocument,
} from '../../../../services/coreApi.js';
import {
  EMPTY_FORM,
  EMPTY_UPLOAD_FORM,
  STATUS_LABELS,
  buildPayload,
  filterDocumentsByTab,
  formFromDocument,
  statusesForFilterTab,
} from '../knowledgeStudioData.js';

/**
 * Data layer for the IA · Knowledge Studio view. Owns the document list, the
 * status/visibility filters, the editor + upload forms and the RAG smoke-test
 * state, plus every mutation handler extracted verbatim from the legacy
 * `KnowledgeStudio`.
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useKnowledgeStudioData({ session, tenant }) {
  const tenantId = tenant?.id;
  const confirm = useConfirm();

  const [documents, setDocuments] = useState([]);
  const [filterTab, setFilterTab] = useState('all');
  const [visibilityFilter, setVisibilityFilter] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  const [storage, setStorage] = useState(null);
  const [storageError, setStorageError] = useState(null);
  const [isStorageLoading, setIsStorageLoading] = useState(false);

  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [uploadForm, setUploadForm] = useState(EMPTY_UPLOAD_FORM);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const [ragOpen, setRagOpen] = useState(false);
  const [ragQuestion, setRagQuestion] = useState('');
  const [ragIncludeAgentsOnly, setRagIncludeAgentsOnly] = useState(false);
  const [ragResult, setRagResult] = useState(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  const loadDocuments = useCallback(() => {
    if (!tenantId) return;
    setIsLoading(true);
    // codex P2 (UI-016.2 review): client-only tab filtering can hide matching
    // rows when a tenant has > 250 documents, because the API applies its
    // `limit 250` AFTER the status filter — so a missing `status` query
    // returns the latest 250 across statuses, and the older rows with the
    // status the user selected get truncated. Forward the active tab's
    // status (when single-valued) to the API so each tab gets up to 250 of
    // ITS status. The "all" tab keeps the cross-status latest 250.
    const tabStatuses = statusesForFilterTab(filterTab);
    const statusParam = tabStatuses && tabStatuses.length === 1 ? tabStatuses[0] : '';
    listKnowledgeDocuments(session, tenantId, {
      visibility: visibilityFilter,
      status: statusParam,
    })
      .then((rows) => setDocuments(Array.isArray(rows) ? rows : []))
      .catch((error) => setNotice({ type: 'error', text: error.message }))
      .finally(() => setIsLoading(false));
  }, [session, tenantId, visibilityFilter, filterTab]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const loadStorage = useCallback(() => {
    if (!tenantId) return;
    setIsStorageLoading(true);
    setStorageError(null);
    getKnowledgeStorageSettings(session, tenantId)
      .then((response) => setStorage(response))
      .catch((error) => {
        // Storage may be 403 for some roles (read-only viewers without
        // knowledge_storage.read); the table view should still render.
        setStorage(null);
        setStorageError(error.message);
      })
      .finally(() => setIsStorageLoading(false));
  }, [session, tenantId]);

  useEffect(() => {
    loadStorage();
  }, [loadStorage]);

  const filteredDocuments = useMemo(
    () => filterDocumentsByTab(documents, filterTab),
    [documents, filterTab],
  );

  const actions = {
    setFilterTab,
    setVisibilityFilter,
    setUploadForm,
    setRagQuestion,
    setRagIncludeAgentsOnly,
    refresh: () => {
      loadDocuments();
      loadStorage();
    },
    refreshStorage: loadStorage,
    dismissNotice: () => setNotice(null),
    openCreate: () => {
      setEditingId(null);
      setForm(EMPTY_FORM);
      setEditorOpen(true);
    },
    openEdit: (document) => {
      setEditingId(document.id);
      setForm(formFromDocument(document));
      setEditorOpen(true);
    },
    closeEditor: () => setEditorOpen(false),
    setFormField: (field, value) => setForm((current) => ({ ...current, [field]: value })),
    openUpload: () => {
      setUploadForm(EMPTY_UPLOAD_FORM);
      setUploadOpen(true);
    },
    closeUpload: () => setUploadOpen(false),
    openRag: () => setRagOpen(true),
    closeRag: () => setRagOpen(false),
    async submit() {
      if (!tenantId || !form.title.trim()) return;
      setIsSaving(true);
      setNotice(null);
      try {
        const payload = buildPayload(form);
        if (editingId) {
          await updateKnowledgeDocument(session, tenantId, editingId, payload);
          setNotice({ type: 'success', text: 'Documento actualizado.' });
        } else {
          await createKnowledgeDocument(session, tenantId, payload);
          setNotice({ type: 'success', text: 'Documento creado en draft.' });
        }
        setEditorOpen(false);
        setEditingId(null);
        setForm(EMPTY_FORM);
        loadDocuments();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsSaving(false);
      }
    },
    async changeStatus(document, nextStatus) {
      setNotice(null);
      try {
        await updateKnowledgeDocument(session, tenantId, document.id, { status: nextStatus });
        setNotice({
          type: 'success',
          text: `Estado cambiado a ${STATUS_LABELS[nextStatus] || nextStatus}.`,
        });
        loadDocuments();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      }
    },
    async runIndexing(document) {
      setNotice(null);
      try {
        const indexed = await indexKnowledgeDocument(session, tenantId, document.id);
        const chunkCount =
          indexed.indexing?.chunk_count || indexed.metadata?.chunk_count || 0;
        setNotice({
          type: 'success',
          text: `Documento indexado y activado con ${chunkCount} chunks.`,
        });
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        loadDocuments();
      }
    },
    async removeDocument(document) {
      setNotice(null);
      const ok = await confirm({
        title: 'Eliminar documento',
        body: `¿Eliminar el documento "${document.title}"?`,
        danger: true,
      });
      if (!ok) return;
      try {
        await deleteKnowledgeDocument(session, tenantId, document.id);
        if (editingId === document.id) {
          setEditingId(null);
          setForm(EMPTY_FORM);
          setEditorOpen(false);
        }
        setNotice({ type: 'success', text: 'Documento eliminado.' });
        loadDocuments();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      }
    },
    async upload() {
      if (!tenantId || !uploadForm.file || !uploadForm.title.trim()) return;
      setIsUploading(true);
      setNotice(null);
      try {
        const uploaded = await uploadKnowledgeDocument(session, tenantId, uploadForm);
        let text;
        if (uploaded.content || uploaded.metadata?.extracted_text) {
          text = 'Archivo guardado; texto extraído. Ya puedes indexarlo.';
        } else if (uploaded._extraction_pending || uploaded.metadata?.extraction_pending) {
          text =
            'Archivo guardado. El texto se extraerá en segundo plano (PDF/DOCX). Refresca en unos segundos y luego indexa.';
        } else {
          text = 'Archivo guardado. Agrega el texto manualmente antes de indexar.';
        }
        setNotice({ type: 'success', text });
        setUploadForm(EMPTY_UPLOAD_FORM);
        setUploadOpen(false);
        loadDocuments();
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsUploading(false);
      }
    },
    async evaluateRetrieval() {
      if (!tenantId || !ragQuestion.trim()) return;
      setIsEvaluating(true);
      setNotice(null);
      try {
        const result = await evaluateIntent(session, tenantId, {
          question: ragQuestion.trim(),
          include_agents_only: ragIncludeAgentsOnly,
        });
        setRagResult(result);
        setNotice({
          type: result.sufficient_context ? 'success' : 'info',
          text: result.sufficient_context
            ? 'Respuesta RAG generada con evidencia trazable.'
            : 'Sin evidencia suficiente: escalar a humano.',
        });
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsEvaluating(false);
      }
    },
  };

  return {
    state: {
      tenantId,
      documents,
      filteredDocuments,
      filterTab,
      visibilityFilter,
      isLoading,
      notice,
      storage,
      storageError,
      isStorageLoading,
      form,
      editingId,
      editorOpen,
      isSaving,
      uploadForm,
      uploadOpen,
      isUploading,
      ragOpen,
      ragQuestion,
      ragIncludeAgentsOnly,
      ragResult,
      isEvaluating,
    },
    actions,
  };
}
