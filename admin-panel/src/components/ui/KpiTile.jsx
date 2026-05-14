import styles from './KpiTile.module.css';

/**
 * KpiTile — KPI card used in dashboards and platform-owner views.
 *
 * @param {Object} props
 * @param {string} props.label
 * @param {React.ReactNode} props.value
 * @param {React.ReactNode} [props.delta] Trend delta (e.g. "+12% vs 7d").
 * @param {'up'|'down'|'flat'} [props.trend='flat']
 * @param {React.ReactNode} [props.footnote]
 * @param {React.ReactNode} [props.icon]
 */
export function KpiTile({
  label,
  value,
  delta,
  trend = 'flat',
  footnote,
  icon,
  className = '',
}) {
  return (
    <article className={[styles.tile, className].filter(Boolean).join(' ')}>
      <header className={styles.head}>
        <span className={styles.label}>{label}</span>
        {icon ? <span className={styles.icon} aria-hidden="true">{icon}</span> : null}
      </header>
      <div className={styles.value}>{value}</div>
      {delta ? (
        <div className={[styles.delta, styles[`delta--${trend}`]].join(' ')} role="note">
          <span className={styles.deltaArrow} aria-hidden="true">
            {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '–'}
          </span>
          <span>{delta}</span>
        </div>
      ) : null}
      {footnote ? <p className={styles.footnote}>{footnote}</p> : null}
    </article>
  );
}
