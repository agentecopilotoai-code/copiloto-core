import { KpiTile } from '../ui/KpiTile.jsx';

/**
 * Calcula el delta porcentual y la tendencia entre dos periodos.
 *
 * @param {number} current
 * @param {number} previous
 * @param {boolean} invertTrend Si `true`, una subida cuenta como tendencia negativa
 *   (útil para métricas donde "menos es mejor", p. ej. no-show rate).
 * @returns {{ delta: string|null, trend: 'up'|'down'|'flat' }}
 */
export function computeDelta(current, previous, invertTrend = false) {
  if (
    typeof current !== 'number'
    || typeof previous !== 'number'
    || Number.isNaN(current)
    || Number.isNaN(previous)
    || previous === 0
  ) {
    return { delta: null, trend: 'flat' };
  }
  const pct = ((current - previous) / Math.abs(previous)) * 100;
  let trend = pct > 0.5 ? 'up' : pct < -0.5 ? 'down' : 'flat';
  if (invertTrend && trend !== 'flat') {
    trend = trend === 'up' ? 'down' : 'up';
  }
  const sign = pct > 0 ? '+' : '';
  return { delta: `${sign}${pct.toFixed(1)}% vs periodo previo`, trend };
}

/**
 * KpiCardWithDelta — KPI con delta calculado a partir de `current`/`previous`.
 *
 * Envuelve `KpiTile` (UI-001) y le añade la lógica de tendencia. No hace fetch.
 *
 * @param {Object} props
 * @param {string} props.label
 * @param {React.ReactNode} props.value Valor ya formateado para mostrar.
 * @param {number} [props.current] Valor numérico del periodo actual.
 * @param {number} [props.previous] Valor numérico del periodo previo.
 * @param {boolean} [props.invertTrend=false]
 * @param {React.ReactNode} [props.footnote]
 * @param {React.ReactNode} [props.icon]
 */
export function KpiCardWithDelta({
  label,
  value,
  current,
  previous,
  invertTrend = false,
  footnote,
  icon,
}) {
  const { delta, trend } = computeDelta(current, previous, invertTrend);
  return (
    <KpiTile
      label={label}
      value={value}
      delta={delta}
      trend={trend}
      footnote={footnote}
      icon={icon}
    />
  );
}
