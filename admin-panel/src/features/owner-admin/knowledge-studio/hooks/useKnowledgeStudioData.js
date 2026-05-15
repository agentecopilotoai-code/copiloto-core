import { useCallback, useEffect, useState } from 'react';

import { useConfirm } from '../../../../components/ui/index.js';
import {
  createKnowledgeDocument,
  deleteKnowledgeDocument,
  evaluateIntent,
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
  formFromDocument,
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
  const [statusFilter, setStatusFilter] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState(null);

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
    listKnowledgeDocuments(session, tenantId, {
      status: statusFilter,
      visibility: visibilityFilter,
    })
      .then((rows) => setDocuments(Array.isArray(rows) ? rows : []))
      .catch((error) => setNotice({ type: 'error', text: error.message }))
      .finally(() => setIsLoading(false));
  }, [session, tenantId, statusFilter, visibilityFilter]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const actions = {
    setStatusFilter,
    setVisibilityFilter,
    setUploadForm,
    setRagQuestion,
    setRagIncludeAgentsOnly,
    refresh: loadDocuments,
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
      statusFilter,
      visibilityFilter,
      isLoading,
      notice,
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
