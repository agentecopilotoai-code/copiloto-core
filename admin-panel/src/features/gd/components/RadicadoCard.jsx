/**
 * RadicadoCard — tarjeta resumen de un radicado.
 *
 * Usado en listas (Mi buzón, Cola Ventanilla, Búsqueda global). Cuando se
 * clickea, navega a la ficha completa `/gd/ventanilla/radicados/{id}`.
 *
 * No incluye datos del solicitante por defecto (RNF-017: cero PII visible
 * en lugares públicos). Si `mostrarTercero=true`, muestra solo iniciales.
 */
import React from 'react';

import { TerminoVencimientoBadge } from './TerminoVencimientoBadge.jsx';

const ESTADO_BADGE = Object.freeze({
  radicado: 'neutral',
  en_gestion: 'info',
  en_revision: 'info',
  cerrado: 'ok',
  anulado: 'danger',
  proximo_vencer: 'warn',
  vencido: 'danger',
});

export function RadicadoCard({
  radicado,
  onClick,
  mostrarTercero = false,
}) {
  if (!radicado) return null;
  const {
    id,
    numero_radicado,
    asunto,
    tipo_radicado,
    estado,
    fecha_radicacion,
    canal_nombre,
    dependencia_actual_nombre,
    tercero_iniciales,
    dias_restantes,
    termino_dias,
  } = radicado;

  const badgeTone = ESTADO_BADGE[estado] || 'neutral';

  return (
    <button
      type="button"
      className="card radicado-card"
      data-testid="radicado-card"
      onClick={() => onClick?.(id)}
      style={{
        textAlign: 'left',
        cursor: onClick ? 'pointer' : 'default',
        width: '100%',
        border: '1px solid var(--border-default)',
        padding: 'var(--s-4)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s-3)' }}>
        <span className="num" style={{ fontFamily: 'var(--font-mono)' }}>
          {numero_radicado}
        </span>
        <span className={`badge ${badgeTone}`}>{estado}</span>
        <span className="badge neutral no-dot">{tipo_radicado}</span>
        {canal_nombre && (
          <span className="muted" style={{ fontSize: 11.5 }}>
            · {canal_nombre}
          </span>
        )}
        <span style={{ marginLeft: 'auto' }}>
          {Number.isFinite(dias_restantes) && (
            <TerminoVencimientoBadge
              diasRestantes={dias_restantes}
              terminoTotal={termino_dias}
              compact
            />
          )}
        </span>
      </div>
      <div style={{ marginTop: 'var(--s-2)', fontWeight: 600 }}>{asunto}</div>
      <div
        className="muted"
        style={{ marginTop: 4, fontSize: 12 }}
      >
        {dependencia_actual_nombre && <>📁 {dependencia_actual_nombre} · </>}
        {mostrarTercero && tercero_iniciales && <>👤 {tercero_iniciales} · </>}
        🕒 {fmtFecha(fecha_radicacion)}
      </div>
    </button>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default RadicadoCard;
