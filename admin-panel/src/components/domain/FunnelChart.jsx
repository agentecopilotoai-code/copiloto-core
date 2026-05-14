import styles from './FunnelChart.module.css';

function pct(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return Math.max(0, Math.min(100, value));
}

/**
 * FunnelChart — gráfico de embudo / desglose de conversión presentacional.
 *
 * Genérico: recibe un array `segments` y pinta una barra horizontal por
 * segmento, con su etiqueta, porcentaje y conteo. El ancho de la barra es
 * proporcional al `percent` (o, si falta, al `value` relativo al máximo).
 * Sin estado, sin fetch — los tokens visuales salen 100% de `var(--...)`.
 *
 * @param {Object} props
 * @param {Array<{ label: string, value?: number, percent?: number, count?: number, hint?: string }>} props.segments
 * @param {string} [props.ariaLabel='Embudo de conversión']
 * @param {React.ReactNode} [props.emptyLabel='Sin datos en el rango.']
 */
export function FunnelChart({
  segments = [],
  ariaLabel = 'Embudo de conversión',
  emptyLabel = 'Sin datos en el rango.',
}) {
  if (!Array.isArray(segments) || segments.length === 0) {
    return <p className={styles.empty}>{emptyLabel}</p>;
  }

  const maxValue = Math.max(
    1,
    ...segments.map((seg) => (typeof seg.value === 'number' ? seg.value : 0)),
  );

  return (
    <ul className={styles.list} aria-label={ariaLabel}>
      {segments.map((seg) => {
        const explicitPct = pct(seg.percent);
        const widthPct =
          explicitPct != null
            ? explicitPct
            : typeof seg.value === 'number'
              ? Math.max((seg.value / maxValue) * 100, 2)
              : 0;
        return (
          <li className={styles.row} key={seg.label}>
            <div className={styles.head}>
              <span className={styles.label}>{seg.label}</span>
              <span className={styles.value}>
                {explicitPct != null ? `${explicitPct.toFixed(0)}%` : null}
                {typeof seg.count === 'number' ? (
                  <span className={styles.count}>
                    {explicitPct != null ? ' · ' : ''}
                    {new Intl.NumberFormat('es-CO').format(seg.count)}
                  </span>
                ) : null}
              </span>
            </div>
            <div className={styles.track}>
              <div
                className={styles.fill}
                style={{ width: `${widthPct}%` }}
                role="presentation"
              />
            </div>
            {seg.hint ? <span className={styles.hint}>{seg.hint}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}
