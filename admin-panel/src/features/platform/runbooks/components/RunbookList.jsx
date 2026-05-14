import { Card, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../Runbooks.module.css';

function formatSize(bytes) {
  const kb = (Number(bytes) || 0) / 1024;
  return `${kb.toFixed(1)} KB`;
}

/**
 * Grid of runbook cards. Each card opens the runbook viewer on click; the
 * keyboard path (Enter / Space) is wired so the catalogue is usable without a
 * mouse.
 *
 * @param {{ runbooks: Array<object>, onSelect: (slug: string) => void }} props
 */
export function RunbookList({ runbooks, onSelect }) {
  if (!runbooks || runbooks.length === 0) {
    return (
      <EmptyState
        title="Sin runbooks"
        description="Ningún runbook coincide con la búsqueda o la categoría seleccionada."
      />
    );
  }

  return (
    <ul className={styles.grid} aria-label="Catálogo de runbooks">
      {runbooks.map((runbook) => (
        <li key={runbook.slug}>
          <Card
            as="article"
            tone="alt"
            padding="md"
            interactive
            className={styles.cardClickable}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(runbook.slug)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelect(runbook.slug);
              }
            }}
          >
            <div className={styles.cardHead}>
              <StatusBadge tone="accent">{runbook.category}</StatusBadge>
              <span className={styles.cardSize}>{formatSize(runbook.size_bytes)}</span>
            </div>
            <h3 className={styles.cardTitle}>{runbook.title}</h3>
            <span className={styles.cardSlug}>{runbook.filename}</span>
          </Card>
        </li>
      ))}
    </ul>
  );
}
