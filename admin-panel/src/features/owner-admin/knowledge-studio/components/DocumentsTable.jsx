import {
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  FormField,
  StatusBadge,
  Tabs,
} from '../../../../components/ui/index.js';
import {
  DOCUMENT_FILTER_TABS,
  STATUS_LABELS,
  STATUS_OPTIONS,
  STATUS_TONE,
  VISIBILITY_OPTIONS,
  chunkCount,
  countDocumentsByTab,
  documentSummary,
  embeddingProviderBadge,
  extractionStatusBadge,
  formatDate,
  isAwaitingExtraction,
  originLabel,
} from '../knowledgeStudioData.js';
import styles from '../KnowledgeStudio.module.css';

/**
 * Knowledge documents table with status / visibility filters. Reuses
 * `DataTable` + `Tabs`; presentational — all state and the row actions come
 * from the `useKnowledgeStudioData` hook via props.
 *
 * UI-016.2: redesign aligned with
 * `docs/HTML DESIGN/Transversales/18 _ IA _ Knowledge Studio.html` — filter
 * tabs (Todos / Activos / Indexando / Fallidos) derived from the data, plus
 * the canonical 6 columns Documento / Tipo / Chunks / Origen / Estado /
 * Actualizado, followed by row actions.
 *
 * @param {{
 *   documents: Array<object>,
 *   filteredDocuments: Array<object>,
 *   filterTab: string,
 *   visibilityFilter: string,
 *   isLoading: boolean,
 *   onFilterTabChange: (value: string) => void,
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
  filteredDocuments,
  filterTab,
  visibilityFilter,
  isLoading,
  onFilterTabChange,
  onVisibilityFilterChange,
  onChangeStatus,
  onIndex,
  onEdit,
  onRemove,
  onRefresh,
}) {
  // codex P2 (UI-016.2 review): once the status filter is server-side, the
  // loaded `documents` array only contains rows for the active tab. Showing
  // per-tab counts derived from that list would be misleading for inactive
  // tabs (they'd all show 0). Only badge the ACTIVE tab — its count is
  // accurate against the API's `limit 250` for that status.
  const counts = countDocumentsByTab(documents);
  const tabItems = DOCUMENT_FILTER_TABS.map((tab) => ({
    value: tab.value,
    label: tab.label,
    badge: tab.value === filterTab ? String(counts[tab.value] ?? 0) : null,
  }));

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
    {
      key: 'chunks',
      header: 'Chunks',
      accessor: (row) => {
        const count = chunkCount(row);
        return count == null ? '—' : count;
      },
    },
    {
      key: 'origin',
      header: 'Origen',
      accessor: (row) => <span className={styles.originCell}>{originLabel(row)}</span>,
    },
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
        subtitle={`${filteredDocuments.length} visibles para este tenant.`}
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

      <Tabs
        variant="pill"
        items={tabItems}
        value={filterTab}
        onChange={onFilterTabChange}
        className={styles.filterTabs}
      />

      <div className={styles.filters}>
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
      ) : filteredDocuments.length === 0 ? (
        <EmptyState
          title="Sin documentos"
          description="No hay documentos con esos filtros. Sube un archivo o crea uno manualmente."
        />
      ) : (
        <DataTable
          caption="Documentos de conocimiento del tenant"
          columns={columns}
          rows={filteredDocuments}
          rowKey={(row) => row.id}
        />
      )}
    </Card>
  );
}
