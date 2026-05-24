/**
 * PQRSDStatusChip — muestra la tipología PQRSD según `tipo`.
 *
 * Tipos según Decreto 1166/2016:
 *  - P (petición), Q (queja), R (reclamo), S (sugerencia), D (denuncia).
 *
 * Visual: chip compacto con glyph de 1 letra + label.
 * Mapeo de colores definido en `portal.css` (`.pqrsd-chip.tipo-P/Q/R/S/D`).
 */
import React from 'react';

const LABELS = Object.freeze({
  P: 'Petición',
  Q: 'Queja',
  R: 'Reclamo',
  S: 'Sugerencia',
  D: 'Denuncia',
});

export function PQRSDStatusChip({ tipo, withLabel = true, className = '' }) {
  const code = String(tipo || '').toUpperCase().slice(0, 1);
  const valid = code in LABELS;
  if (!valid) return null;
  return (
    <span
      className={`pqrsd-chip tipo-${code} ${className}`}
      data-testid="pqrsd-status-chip"
      title={LABELS[code]}
    >
      <span className="glyph" aria-hidden="true">{code}</span>
      {withLabel && <span className="label">{LABELS[code]}</span>}
    </span>
  );
}

export default PQRSDStatusChip;
