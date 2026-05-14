import styles from './EmptyState.module.css';

/**
 * EmptyState — shown when a list/table/grid has no data.
 *
 * @param {Object} props
 * @param {React.ReactNode} [props.icon]
 * @param {React.ReactNode} props.title
 * @param {React.ReactNode} [props.description]
 * @param {React.ReactNode} [props.action] CTA placed below the description.
 * @param {'sm'|'md'|'lg'} [props.size='md']
 */
export function EmptyState({ icon, title, description, action, size = 'md', className = '' }) {
  return (
    <div
      role="status"
      className={[styles.empty, styles[`empty--${size}`], className].filter(Boolean).join(' ')}
    >
      {icon ? <div className={styles.icon} aria-hidden="true">{icon}</div> : null}
      <h3 className={styles.title}>{title}</h3>
      {description ? <p className={styles.description}>{description}</p> : null}
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
