import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { KIND_LABELS, KIND_TONES, formatDate } from '../segmentsData.js';
import styles from '../SegmentsModule.module.css';

/**
 * Segments list as a `DataTable`. Presentational — the segments come from the
 * `useSegmentsData` hook; row actions (select / edit / preview / refresh /
 * delete) are callbacks. The per-segment action gating (system segments cannot
 * be deleted; only dynamic segments can be refreshed) mirrors the legacy
 * `SegmentsModule` verbatim.
 *
 * @param {{
 *   segments: Array<object>,
 *   selectedId: string | null,
 *   isBusy: boolean,
 *   onSelect: (id: string) => void,
 *   onEdit: (segment: object) => void,
 *   onPreview: () => void,
 *   onRefresh: () => void,
 *   onDelete: () => void,
 * }} props
 */
export function SegmentsList({
  segments,
  selectedId,
  isBusy,
  onSelect,
  onEdit,
  onPreview,
  onRefresh,
  onDelete,
}) {
  const columns = [
    {
      key: 'name',
      header: 'Segmento',
      accessor: (row) => (
        <div className={styles.cellMain}>
          <strong>{row.name}</strong>
          <span className={styles.cellMeta}>
            {row.description || (row.is_system ? 'Segmento del sistema' : 'Segmento personalizado')}
          </span>
        </div>
      ),
    },
    {
      key: 'kind',
      header: 'Tipo',
      accessor: (row) => (
        <StatusBadge tone={KIND_TONES[row.kind] || 'neutral'}>
          {KIND_LABELS[row.kind] || row.kind}
        </StatusBadge>
      ),
    },
    {
      key: 'contact_count',
      header: 'Contactos',
      align: 'right',
      accessor: (row) => row.contact_count ?? 0,
    },
    {
      key: 'last_refreshed_at',
      header: 'Refrescado',
      accessor: (row) => formatDate(row.last_refreshed_at),
    },
    {
      key: 'actions',
      header: 'Acciones',
      align: 'right',
      accessor: (row) => {
        const isSelected = row.id === selectedId;
        return (
          <div className={styles.rowActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={isBusy}
              onClick={(event) => {
                event.stopPropagation();
                onEdit(row);
              }}
            >
              Editar
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={!isSelected || isBusy}
              onClick={(event) => {
                event.stopPropagation();
                onPreview();
              }}
            >
              Previsualizar
            </button>
            {row.kind === 'dynamic' ? (
              <button
                type="button"
                className={styles.secondaryButton}
                disabled={!isSelected || isBusy}
                onClick={(event) => {
                  event.stopPropagation();
                  onRefresh();
                }}
              >
                Refrescar
              </button>
            ) : null}
            {!row.is_system ? (
              <button
                type="button"
                className={styles.dangerButton}
                disabled={!isSelected || isBusy}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete();
                }}
              >
                Eliminar
              </button>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title={`Segmentos (${segments.length})`}
        subtitle="Los segmentos reutilizan reglas (ej. «Sin visita en 60+ días») como destinatarios de campañas y filtros de contactos. Selecciona uno para previsualizar o recalcular sus contactos."
      />
      {segments.length === 0 ? (
        <EmptyState
          title="No hay segmentos todavía"
          description="Crea el primero con «Nuevo segmento». Tu tenant ya viene con 5 segmentos preconfigurados."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={segments}
          rowKey={(row) => row.id}
          onRowClick={(row) => onSelect(row.id)}
          caption="Segmentos del tenant"
        />
      )}
    </Card>
  );
}
