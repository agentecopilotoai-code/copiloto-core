import styles from './AlertBanner.module.css';

const TONES = ['info', 'warning', 'danger', 'success'];

/**
 * AlertBanner — inline banner for dashboard alerts, notices and operational
 * warnings. Tone drives the accent colour; the optional `action` slot holds a
 * CTA (usually a link to the relevant module).
 *
 * @param {Object} props
 * @param {'info'|'warning'|'danger'|'success'} [props.tone='info']
 * @param {React.ReactNode} props.title
 * @param {React.ReactNode} [props.children] Description body.
 * @param {React.ReactNode} [props.action] CTA rendered on the trailing edge.
 * @param {React.ReactNode} [props.icon]
 */
export function AlertBanner({ tone = 'info', title, children, action, icon, className = '' }) {
  const safeTone = TONES.includes(tone) ? tone : 'info';
  const classes = [styles.banner, styles[`banner--${safeTone}`], className]
    .filter(Boolean)
    .join(' ');

  return (
    <div role="status" className={classes}>
      {icon ? (
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <div className={styles.body}>
        <p className={styles.title}>{title}</p>
        {children ? <div className={styles.description}>{children}</div> : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
