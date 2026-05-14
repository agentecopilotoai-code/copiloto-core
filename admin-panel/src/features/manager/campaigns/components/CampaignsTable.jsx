import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { formatDate, statusLabel, statusTone } from '../campaignsData.js';
import styles from '../CampaignsModule.module.css';

/**
 * Campaigns list as a `DataTable`. Presentational — the campaigns come from the
 * `useCampaignsData` hook; row actions (select / edit / preview / launch /
 * cancel) are callbacks. The per-status action gating mirrors the legacy
 * `CampaignsModule` verbatim.
 *
 * @param {{
 *   campaigns: Array<object>,
 *   selectedId: string | null,
 *   isBusy: boolean,
 *   onSelect: (id: string) => void,
 *   onEdit: (campaign: object) => void,
 *   onPreview: () => void,
 *   onLaunch: () => void,
 *   onCancel: () => void,
 * }} props
 */
export function CampaignsTable({
  campaigns,
  selectedId,
  isBusy,
  onSelect,
  onEdit,
  onPreview,
  onLaunch,
  onCancel,
}) {
  const columns = [
    {
      key: 'name',
      header: 'Campaña',
      accessor: (row) => (
        <div className={styles.cellMain}>
          <strong>{row.name}</strong>
          <span className={styles.cellMeta}>
            {row.recipient_count || 0} destinatarios
          </span>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={statusTone(row.status)}>{statusLabel(row.status)}</StatusBadge>
      ),
    },
    {
      key: 'scheduled_at',
      header: 'Envío programado',
      accessor: (row) =>
        row.scheduled_at ? formatDate(row.scheduled_at) : 'Sin programar',
    },
    {
      key: 'sent',
      header: 'Enviados',
      align: 'right',
      accessor: (row) => `${row.sent_count || 0} / ${row.recipient_count || 0}`,
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
              disabled={row.status !== 'draft' || isBusy}
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
              Destinatarios
            </button>
            {['draft', 'scheduled'].includes(row.status) ? (
              <button
                type="button"
                className={styles.primaryButton}
                disabled={!isSelected || isBusy}
                onClick={(event) => {
                  event.stopPropagation();
                  onLaunch();
                }}
              >
                {row.status === 'scheduled' ? 'Reprogramar' : 'Programar envío'}
              </button>
            ) : null}
            {!['completed', 'cancelled'].includes(row.status) ? (
              <button
                type="button"
                className={styles.dangerButton}
                disabled={!isSelected || isBusy}
                onClick={(event) => {
                  event.stopPropagation();
                  onCancel();
                }}
              >
                Cancelar
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
        title={`Campañas (${campaigns.length})`}
        subtitle="Las campañas envían un template aprobado a contactos con opt-in válido. Selecciona una para ver sus métricas de entrega."
      />
      {campaigns.length === 0 ? (
        <EmptyState
          title="No hay campañas todavía"
          description="Crea la primera campaña con «Nueva campaña»."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={campaigns}
          rowKey={(row) => row.id}
          onRowClick={(row) => onSelect(row.id)}
          caption="Campañas del tenant"
        />
      )}
    </Card>
  );
}
