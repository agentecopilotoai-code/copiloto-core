import styles from './Pagination.module.css';

/**
 * Pagination — page navigator with prev/next + numbered window.
 *
 * @param {Object} props
 * @param {number} props.page Current page (1-based).
 * @param {number} props.pageCount Total pages.
 * @param {(page: number) => void} props.onPageChange
 * @param {number} [props.siblings=1] Pages to show around the current page.
 */
export function Pagination({ page, pageCount, onPageChange, siblings = 1, className = '' }) {
  if (pageCount <= 1) return null;

  const items = buildWindow(page, pageCount, siblings);

  return (
    <nav className={[styles.pagination, className].filter(Boolean).join(' ')} aria-label="Paginación">
      <button
        type="button"
        className={styles.btn}
        onClick={() => onPageChange(Math.max(1, page - 1))}
        disabled={page <= 1}
        aria-label="Página anterior"
      >
        ‹
      </button>
      <ul className={styles.list}>
        {items.map((item, idx) =>
          item === '…' ? (
            <li key={`gap-${idx}`} className={styles.gap} aria-hidden="true">
              …
            </li>
          ) : (
            <li key={item}>
              <button
                type="button"
                className={[styles.page, item === page ? styles['page--active'] : ''].filter(Boolean).join(' ')}
                onClick={() => onPageChange(item)}
                aria-current={item === page ? 'page' : undefined}
              >
                {item}
              </button>
            </li>
          ),
        )}
      </ul>
      <button
        type="button"
        className={styles.btn}
        onClick={() => onPageChange(Math.min(pageCount, page + 1))}
        disabled={page >= pageCount}
        aria-label="Página siguiente"
      >
        ›
      </button>
    </nav>
  );
}

function buildWindow(page, pageCount, siblings) {
  const range = (start, end) => Array.from({ length: end - start + 1 }, (_, i) => start + i);
  const left = Math.max(2, page - siblings);
  const right = Math.min(pageCount - 1, page + siblings);
  const items = [1];
  if (left > 2) items.push('…');
  items.push(...range(left, right));
  if (right < pageCount - 1) items.push('…');
  if (pageCount > 1) items.push(pageCount);
  return items;
}
