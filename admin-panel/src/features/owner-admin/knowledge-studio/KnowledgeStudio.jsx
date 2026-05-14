import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { DocumentDetailDrawer } from './components/DocumentDetailDrawer.jsx';
import { DocumentUploader } from './components/DocumentUploader.jsx';
import { DocumentsTable } from './components/DocumentsTable.jsx';
import { RagSmokeTest } from './components/RagSmokeTest.jsx';
import { useKnowledgeStudioData } from './hooks/useKnowledgeStudioData.js';
import { hasLocalHashActive } from './knowledgeStudioData.js';
import styles from './KnowledgeStudio.module.css';

/**
 * UI-007.10 — IA · Knowledge Studio.
 *
 * Refactor of the legacy `KnowledgeStudio` (486 LOC) into a feature with an
 * orchestrator + `useKnowledgeStudioData` hook + pure `knowledgeStudioData.js`
 * + the split components: `DocumentsTable`, `DocumentUploader`,
 * `DocumentDetailDrawer` and `RagSmokeTest`. Document CRUD, indexing, the file
 * upload flow and the RAG smoke test are preserved verbatim. Gated by
 * `knowledge.read`; the backend remains the authority.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/18 _ IA · Knowledge Studio.html`.
 * Declared difference: the HTML's "Storage" card (bucket / size) belongs to the
 * separate `knowledge-storage` module and is not duplicated here.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function KnowledgeStudio({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });
  const { state, actions } = useKnowledgeStudioData({ session, tenant });

  const editingDocument =
    state.editingId != null
      ? state.documents.find((document) => document.id === state.editingId) || null
      : null;
  const showLocalHashBanner = hasLocalHashActive(state.documents) && state.documents.length > 0;

  return (
    <RequirePermission permissions={permissions} capability="knowledge.read">
      <section className={styles.page}>
        <PageHeader
          eyebrow="IA & Canales"
          title={module?.label || 'Knowledge Studio'}
          description="Documentos que el bot usa para responder. Cada uno se indexa en chunks, se versiona y se puede testear contra preguntas reales antes de activarlo."
          actions={
            <div className={styles.headerActions}>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.openRag}
                disabled={!state.tenantId}
              >
                Test RAG
              </button>
              <button
                type="button"
                className={styles.primaryButton}
                onClick={actions.openUpload}
                disabled={!state.tenantId}
              >
                Subir documento
              </button>
            </div>
          }
        />

        {showLocalHashBanner ? (
          <AlertBanner
            tone="warning"
            title="Proveedor léxico activo"
            description="Los documentos indexados usan embeddings SHA-256 (local_hash); la búsqueda semántica no está disponible. Configura RAG_EMBEDDING_PROVIDER en el servidor y usa «Re-indexar todos» desde el wizard del tenant."
          />
        ) : null}

        {state.notice ? (
          <AlertBanner
            tone={state.notice.type === 'error' ? 'danger' : state.notice.type === 'info' ? 'info' : 'success'}
            title={state.notice.text}
            action={
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.dismissNotice}
              >
                Cerrar
              </button>
            }
          />
        ) : null}

        {!state.tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para gestionar su base de conocimiento."
            />
          </Card>
        ) : (
          <>
            <div className={styles.toolbar}>
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={actions.openCreate}
              >
                Nuevo documento
              </button>
            </div>
            <DocumentsTable
              documents={state.documents}
              statusFilter={state.statusFilter}
              visibilityFilter={state.visibilityFilter}
              isLoading={state.isLoading}
              onStatusFilterChange={actions.setStatusFilter}
              onVisibilityFilterChange={actions.setVisibilityFilter}
              onChangeStatus={actions.changeStatus}
              onIndex={actions.runIndexing}
              onEdit={actions.openEdit}
              onRemove={actions.removeDocument}
              onRefresh={actions.refresh}
            />
          </>
        )}

        <DocumentDetailDrawer
          open={state.editorOpen}
          form={state.form}
          editingId={state.editingId}
          editingDocument={editingDocument}
          isSaving={state.isSaving}
          onFieldChange={actions.setFormField}
          onSubmit={actions.submit}
          onClose={actions.closeEditor}
        />
        <DocumentUploader
          open={state.uploadOpen}
          uploadForm={state.uploadForm}
          isUploading={state.isUploading}
          onChange={actions.setUploadForm}
          onSubmit={actions.upload}
          onClose={actions.closeUpload}
        />
        <RagSmokeTest
          open={state.ragOpen}
          question={state.ragQuestion}
          includeAgentsOnly={state.ragIncludeAgentsOnly}
          result={state.ragResult}
          isEvaluating={state.isEvaluating}
          onQuestionChange={actions.setRagQuestion}
          onIncludeAgentsOnlyChange={actions.setRagIncludeAgentsOnly}
          onEvaluate={actions.evaluateRetrieval}
          onClose={actions.closeRag}
        />
      </section>
    </RequirePermission>
  );
}
