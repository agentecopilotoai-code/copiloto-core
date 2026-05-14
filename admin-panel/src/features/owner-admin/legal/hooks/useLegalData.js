import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  createLegalDocumentDraft,
  legalDocumentPublicUrl,
  listLegalDocuments,
  publishLegalDocument,
} from '../../../../services/coreApi.js';
import { emptyDraft, groupByKind, publishedByKind } from '../legalData.js';

/**
 * Data layer for the Config · Legal view. Owns the legal-document list and the
 * draft form, plus the mutation handlers extracted verbatim from the legacy
 * `LegalModule` (including the native publish confirm and the append-only
 * versioning flow).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useLegalData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [documents, setDocuments] = useState([]);
  const [form, setForm] = useState(emptyDraft);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await listLegalDocuments(session, tenantId);
      setDocuments(Array.isArray(res?.documents) ? res.documents : []);
    } catch (err) {
      setError(err.message || 'No se pudieron cargar los documentos legales.');
    } finally {
      setLoading(false);
    }
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const grouped = useMemo(() => groupByKind(documents), [documents]);
  const published = useMemo(() => publishedByKind(grouped), [grouped]);

  const publicUrl = useCallback(
    (kind) => (tenantId ? legalDocumentPublicUrl(session, tenantId, kind) : ''),
    [session, tenantId],
  );

  const actions = {
    setFormField: (patch) => setForm((current) => ({ ...current, ...patch })),
    dismissError: () => setError(null),
    dismissInfo: () => setInfo(null),
    refresh,
    async saveDraft() {
      if (!tenantId) return;
      if (!form.title.trim()) {
        setError('El título es obligatorio.');
        return;
      }
      if (!form.content_md.trim()) {
        setError('El contenido en Markdown no puede estar vacío.');
        return;
      }
      setSaving(true);
      setError(null);
      setInfo(null);
      try {
        const created = await createLegalDocumentDraft(session, tenantId, {
          kind: form.kind,
          language: (form.language || 'es').slice(0, 8),
          title: form.title.trim(),
          content_md: form.content_md,
        });
        setInfo(`Borrador v${created.version} creado. Publícalo cuando esté listo.`);
        setForm(emptyDraft());
        await refresh();
      } catch (err) {
        setError(err.message || 'No se pudo crear el borrador.');
      } finally {
        setSaving(false);
      }
    },
    async publish(doc) {
      if (!tenantId) return;
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      if (
        !window.confirm(
          `¿Publicar v${doc.version} de "${doc.title}"? La versión anterior quedará archivada.`,
        )
      ) {
        return;
      }
      setSaving(true);
      setError(null);
      setInfo(null);
      try {
        await publishLegalDocument(session, tenantId, doc.id);
        setInfo(`v${doc.version} publicada. El bot ya enlaza la nueva versión.`);
        await refresh();
      } catch (err) {
        setError(err.message || 'No se pudo publicar el documento.');
      } finally {
        setSaving(false);
      }
    },
  };

  return {
    state: {
      tenantId,
      documents,
      form,
      loading,
      saving,
      error,
      info,
      grouped,
      published,
    },
    publicUrl,
    actions,
  };
}
