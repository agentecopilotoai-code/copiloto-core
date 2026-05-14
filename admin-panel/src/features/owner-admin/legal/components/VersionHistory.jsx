import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { KIND_LABELS, KIND_ORDER, docStatusLabel, docStatusTone } from '../legalData.js';
import styles from '../LegalModule.module.css';

/**
 * Append-only version history per legal kind. Each kind with versions renders a
 * `DataTable`; unpublished versions expose a "Publicar" action. Presentational —
 * the grouped documents come from the `useLegalData` hook.
 *
 * @param {{
 *   grouped: Record<string, Array<object>>,
 *   loading: boolean,
 *   saving: boolean,
 *   onPublish: (doc: object) => void,
 * }} props
 */
export function VersionHistory({ grouped, loading, saving, onPublish }) {
  const columns = [
    { key: 'version', header: 'v', accessor: (row) => row.version },
    { key: 'language', header: 'Idioma', accessor: (row) => row.language },
    { key: 'title', header: 'Título', accessor: (row) => row.title },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={docStatusTone(row)}>{docStatusLabel(row)}</StatusBadge>
      ),
    },
    {
      key: 'created_at',
      header: 'Creado',
      accessor: (row) => new Date(row.created_at).toLocaleString(),
    },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) =>
        !row.published_at ? (
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={saving}
            onClick={() => onPublish(row)}
          >
            Publicar
          </button>
        ) : null,
    },
  ];

  const kindsWithRows = KIND_ORDER.filter((kind) => (grouped[kind] || []).length > 0);

  return (
    <Card padding="md">
      <CardHeader
        title="Historial de versiones"
        subtitle="Las versiones archivadas siguen accesibles para auditoría."
      />
      {loading ? (
        <p className={styles.hint}>Cargando…</p>
      ) : kindsWithRows.length === 0 ? (
        <EmptyState
          title="Sin versiones"
          description="Aún no hay documentos legales. Crea el primer borrador con el editor."
        />
      ) : (
        kindsWithRows.map((kind) => (
          <div key={kind} className={styles.historyGroup}>
            <h4 className={styles.historyTitle}>{KIND_LABELS[kind]}</h4>
            <DataTable
              caption={`Historial de ${KIND_LABELS[kind]}`}
              columns={columns}
              rows={grouped[kind]}
              rowKey={(row) => row.id}
            />
          </div>
        ))
      )}
    </Card>
  );
}
