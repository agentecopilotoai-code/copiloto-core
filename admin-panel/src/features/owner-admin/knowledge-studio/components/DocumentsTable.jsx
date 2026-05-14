import {
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  FormField,
  StatusBadge,
} from '../../../../components/ui/index.js';
import {
  STATUS_LABELS,
  STATUS_OPTIONS,
  STATUS_TONE,
  VISIBILITY_OPTIONS,
  documentSummary,
  embeddingProviderBadge,
  extractionStatusBadge,
  formatDate,
  isAwaitingExtraction,
} from '../knowledgeStudioData.js';
import styles from '../KnowledgeStudio.module.css';

/**
 * Knowledge documents table with status / visibility filters. Reuses
 * `DataTable`; presentational — all state and the row actions come from the
 * `useKnowledgeStudioData` hook via props.
 *
 * @param {{
 *   documents: Array<object>,
 *   statusFilter: string,
 *   visibilityFilter: string,
 *   isLoading: boolean,
 *   onStatusFilterChange: (value: string) => void,
 *   onVisibilityFilterChange: (value: string) => void,
 *   onChangeStatus: (document: object, status: string) => void,
 *   onIndex: (document: object) => void,
 *   onEdit: (document: object) => void,
 *   onRemove: (document: object) => void,
 *   onRefresh: () => void,
 * }} props
 */
export function DocumentsTable({
  documents,
  statusFilter,
  visibilityFilter,
  isLoading,
  onStatusFilterChange,
  onVisibilityFilterChange,
  onChangeStatus,
  onIndex,
  onEdit,
  onRemove,
  onRefresh,
}) {
  const columns = [
    {
      key: 'document',
      header: 'Documento',
      accessor: (row) => (
        <div className={styles.docCell}>
          <strong>{row.title}</strong>
          <span className={styles.docSummary}>{documentSummary(row)}</span>
          {row.metadata?.extraction_error ? (
            <span className={styles.docError}>
              Error de extracción: {row.metadata.extraction_error}
            </span>
          ) : null}
        </div>
      ),
    },
    { key: 'document_type', header: 'Tipo', accessor: (row) => row.document_type },
    { key: 'source_type', header: 'Origen', accessor: (row) => row.source_type },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => {
        const exBadge = extractionStatusBadge(row);
        const embBadge = embeddingProviderBadge(row);
        return (
          <div className={styles.badgeStack}>
            <StatusBadge tone={STATUS_TONE[row.status] || 'neutral'}>
              {STATUS_LABELS[row.status] || row.status}
            </StatusBadge>
            {exBadge ? <StatusBadge tone={exBadge.tone}>{exBadge.label}</StatusBadge> : null}
            {embBadge ? <StatusBadge tone={embBadge.tone}>{embBadge.label}</StatusBadge> : null}
          </div>
        );
      },
    },
    { key: 'updated_at', header: 'Actualizado', accessor: (row) => formatDate(row.updated_at) },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) => {
        const awaiting = isAwaitingExtraction(row);
        return (
          <div className={styles.rowActions}>
            <select
              aria-label={`Cambiar estado de ${row.title}`}
              className={styles.statusSelect}
              value={row.status}
              onChange={(event) => onChangeStatus(row, event.target.value)}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
              <option value="active" disabled>
                Active (solo por indexado)
              </option>
            </select>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={awaiting}
              title={
                awaiting
                  ? 'Espera a que el worker extraiga el texto del archivo antes de indexar.'
                  : 'Indexar documento'
              }
              onClick={() => !awaiting && onIndex(row)}
            >
              {awaiting ? 'Extrayendo…' : 'Indexar'}
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => onEdit(row)}
            >
              Editar
            </button>
            <button
              type="button"
              className={styles.dangerButton}
              onClick={() => onRemove(row)}
            >
              Eliminar
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Documentos"
        subtitle={`${documents.length} visibles para este tenant.`}
        actions={
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={isLoading}
            onClick={onRefresh}
          >
            Refrescar
          </button>
        }
      />

      <div className={styles.filters}>
        <FormField label="Estado">
          <select value={statusFilter} onChange={(e) => onStatusFilterChange(e.target.value)}>
            <option value="">Todos</option>
            <option value="draft">Draft</option>
            <option value="indexing">Indexing</option>
            <option value="active">Active</option>
            <option value="failed">Failed</option>
          </select>
        </FormField>
        <FormField label="Visibilidad">
          <select
            value={visibilityFilter}
            onChange={(e) => onVisibilityFilterChange(e.target.value)}
          >
            <option value="">Todas</option>
            {VISIBILITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </FormField>
      </div>

      {isLoading ? (
        <p className={styles.hint}>Cargando documentos…</p>
      ) : documents.length === 0 ? (
        <EmptyState
          title="Sin documentos"
          description="No hay documentos con esos filtros. Sube un archivo o crea uno manualmente."
        />
      ) : (
        <DataTable
          caption="Documentos de conocimiento del tenant"
          columns={columns}
          rows={documents}
          rowKey={(row) => row.id}
        />
      )}
    </Card>
  );
}
