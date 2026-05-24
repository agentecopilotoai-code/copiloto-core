/**
 * TerminoVencimientoBadge — semáforo de vencimiento para términos legales
 * (PQRSD, correspondencia, tareas con SLA).
 *
 * Regla (GD-API-0042 — alertas críticas):
 *  - "ok"     → días restantes > 25% del término total.
 *  - "warn"   → entre 0% y 25% (próximo a vencer).
 *  - "danger" → 0 días o menos pero aún no vencido (vence hoy).
 *  - "vencida" → vencido (días < 0).
 *
 * Props:
 *  - `diasRestantes` (number): puede ser negativo (vencido).
 *  - `terminoTotal` (number): término legal completo en días hábiles.
 *  - `compact` (boolean): si true, solo dot + texto, sin barra.
 */
import React from 'react';

export function TerminoVencimientoBadge({
  diasRestantes,
  terminoTotal = null,
  compact = false,
  className = '',
}) {
  const d = Number(diasRestantes ?? 0);
  const total = Number(terminoTotal || 0);
  const status = computeStatus(d, total);
  const ratio = computeRatio(d, total);
  const tone = TONE_BY_STATUS[status];

  return (
    <span
      className={`vto-badge ${tone} ${status === 'vencida' ? 'vto-vencida' : ''} ${className}`}
      data-testid="vto-badge"
      data-status={status}
    >
      <span className="vto-dot" aria-hidden="true" />
      {!compact && terminoTotal != null && (
        <span className="vto-bar" aria-hidden="true">
          <i style={{ width: `${Math.round(ratio * 100)}%` }} />
        </span>
      )}
      <span className="vto-text">
        {status === 'vencida' ? `Vencido ${Math.abs(d)}d` : `${d}d`}
      </span>
    </span>
  );
}

const TONE_BY_STATUS = Object.freeze({
  ok: 'vto-ok',
  warn: 'vto-warn',
  danger: 'vto-danger',
  vencida: 'vto-danger',
});

export function computeStatus(diasRestantes, terminoTotal) {
  if (diasRestantes < 0) return 'vencida';
  if (diasRestantes === 0) return 'danger';
  if (!terminoTotal || terminoTotal <= 0) {
    return diasRestantes <= 3 ? 'warn' : 'ok';
  }
  const pct = diasRestantes / terminoTotal;
  if (pct <= 0.25) return 'warn';
  return 'ok';
}

function computeRatio(d, total) {
  if (!total || total <= 0) return 0;
  if (d <= 0) return 1;
  if (d >= total) return 0;
  return 1 - d / total;
}

export default TerminoVencimientoBadge;
