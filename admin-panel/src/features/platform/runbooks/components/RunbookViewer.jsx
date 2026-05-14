import { Modal, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../Runbooks.module.css';

/**
 * Runbook viewer modal. Renders the server-produced HTML from
 * `GET /v1/platform/runbooks/{slug}`.
 *
 * The HTML is safe to inject: it comes from `render_markdown_to_safe_html`
 * (TASK-0076), which fully `html.escape`s every input and only emits a fixed,
 * tag-limited Markdown subset (headings, lists, paragraphs, inline code/bold/
 * italic, scheme-checked links) — no script/style/raw-HTML can survive it. The
 * renderer is shared with the public legal pages.
 *
 * @param {{
 *   open: boolean,
 *   runbook: object | null,
 *   loading: boolean,
 *   error: string | null,
 *   onClose: () => void,
 * }} props
 */
export function RunbookViewer({ open, runbook, loading, error, onClose }) {
  if (!open) return null;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={runbook?.title || 'Runbook'}
      description={
        runbook ? (
          <span className={styles.viewerMeta}>
            <StatusBadge tone="accent">{runbook.category}</StatusBadge>
            <span className={styles.cardSlug}>{runbook.filename}</span>
          </span>
        ) : null
      }
      footer={
        <div className={styles.viewerActions}>
          <button type="button" className={styles.linkButton} onClick={onClose}>
            Cerrar
          </button>
        </div>
      }
    >
      {error ? (
        <p className={styles.viewerError}>{error}</p>
      ) : loading || !runbook ? (
        <p className={styles.muted}>Cargando runbook…</p>
      ) : (
        <div
          className={styles.viewerBody}
          /* Safe: server-rendered by render_markdown_to_safe_html (TASK-0076). */
          dangerouslySetInnerHTML={{ __html: runbook.html }}
        />
      )}
    </Modal>
  );
}
