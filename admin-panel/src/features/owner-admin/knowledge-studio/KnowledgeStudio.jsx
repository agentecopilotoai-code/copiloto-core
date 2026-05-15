import { AlertBanner, Card, EmptyState, PageHeader } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { DocumentDetailDrawer } from './components/DocumentDetailDrawer.jsx';
import { DocumentUploader } from './components/DocumentUploader.jsx';
import { DocumentsTable } from './components/DocumentsTable.jsx';
import { RagSmokeTest } from './components/RagSmokeTest.jsx';
import { StorageSummary } from './components/StorageSummary.jsx';
import { useKnowledgeStudioData } from './hooks/useKnowledgeStudioData.js';
import { hasLocalHashActive } from './knowledgeStudioData.js';
import styles from './KnowledgeStudio.module.css';

/**
 * IA · Knowledge Studio.
 *
 * UI-007.10 split the legacy module into the orchestrator +
 * `useKnowledgeStudioData` hook + pure `knowledgeStudioData.js` + the
 * components `DocumentsTable`, `DocumentUploader`, `DocumentDetailDrawer` and
 * `RagSmokeTest`. UI-016.2 aligns it visually with the redesign in
 * `docs/HTML DESIGN/Transversales/18 _ IA _ Knowledge Studio.html`: filter tabs
 * (Todos / Activos / Indexando / Fallidos) with derived counts, the canonical
 * 6 columns (Documento / Tipo / Chunks / Origen / Estado / Actualizado), and a
 * read-only Storage summary tile below the table.
 *
 * Declared difference: the editable Storage form remains in the dedicated
 * `knowledge-storage` module (capability `knowledge_storage.write`). This view
 * surfaces the current effective configuration as a summary so the operator
 * can see at a glance where the documents live, but never edits credentials
 * from here.
 *
 * Gated by `knowledge.read`; the backend remains the authority.
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
              filteredDocuments={state.filteredDocuments}
              filterTab={state.filterTab}
              visibilityFilter={state.visibilityFilter}
              isLoading={state.isLoading}
              onFilterTabChange={actions.setFilterTab}
              onVisibilityFilterChange={actions.setVisibilityFilter}
              onChangeStatus={actions.changeStatus}
              onIndex={actions.runIndexing}
              onEdit={actions.openEdit}
              onRemove={actions.removeDocument}
              onRefresh={actions.refresh}
            />
            <StorageSummary
              storage={state.storage}
              documentCount={state.documents.length}
              isLoading={state.isStorageLoading}
              error={state.storageError}
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
