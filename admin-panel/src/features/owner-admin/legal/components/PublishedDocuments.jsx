import { Card, CardHeader, StatusBadge } from '../../../../components/ui/index.js';
import { KIND_LABELS, KIND_ORDER } from '../legalData.js';
import styles from '../LegalModule.module.css';

/**
 * "Documentos" panel — the currently-published version per legal kind, with the
 * public URL the bot references. Presentational — `published` + `publicUrl`
 * come from the `useLegalData` hook.
 *
 * @param {{
 *   published: Record<string, object | undefined>,
 *   publicUrl: (kind: string) => string,
 * }} props
 */
export function PublishedDocuments({ published, publicUrl }) {
  return (
    <Card padding="md">
      <CardHeader
        title="Documentos"
        subtitle="Todo es append-only y versionado — publicar archiva la versión anterior automáticamente."
      />
      <ul className={styles.publishedList}>
        {KIND_ORDER.map((kind) => {
          const doc = published[kind];
          const url = publicUrl(kind);
          return (
            <li key={kind} className={styles.publishedRow}>
              <div className={styles.publishedMain}>
                <strong>{KIND_LABELS[kind]}</strong>
                {doc ? (
                  <span className={styles.publishedMeta}>
                    v{doc.version} — publicado {new Date(doc.published_at).toLocaleString()}
                  </span>
                ) : (
                  <span className={styles.publishedMeta}>— sin publicar —</span>
                )}
              </div>
              <div className={styles.publishedSide}>
                {doc ? (
                  <StatusBadge tone="success">v{doc.version}</StatusBadge>
                ) : (
                  <StatusBadge tone="neutral">—</StatusBadge>
                )}
                {doc && url ? (
                  <a href={url} target="_blank" rel="noreferrer" className={styles.publicLink}>
                    Ver página pública ↗
                  </a>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
