/**
 * RadicadoConstanciaPreview — vista imprimible de la constancia (GD-UI-0010).
 *
 * RNF-014/040: la constancia es un documento OFICIAL que se entrega al
 * ciudadano. Lleva el branding institucional (logo + nombre + NIT) y el
 * QR de verificación que apunta a `/gd/verificar/{codigo_verificacion}`
 * (endpoint público sin auth — GD-API-0030).
 *
 * El QR se renderiza como SVG inline para que funcione en impresión
 * sin dependencias externas (qrcode lib es opcional; aquí usamos un
 * generador determinista simple — código real lo reemplaza un servicio).
 */
import React from 'react';

import { InstitutionalLetterhead } from '../components/InstitutionalLetterhead.jsx';

export function RadicadoConstanciaPreview({
  radicado,
  entidad,
  verifyBaseUrl = '/gd/verificar',
}) {
  if (!radicado) {
    return (
      <div className="empty" data-testid="constancia-empty">
        <p className="muted">No hay datos de radicado para mostrar.</p>
      </div>
    );
  }
  const codigo = radicado.codigo_verificacion || radicado.codigo || 'XXXXXXXX';
  const url = `${verifyBaseUrl}/${codigo}`;
  return (
    <article
      className="constancia"
      data-testid="constancia-preview"
      style={{
        background: 'white',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--r-lg)',
        padding: 'var(--s-6)',
        maxWidth: 720,
        margin: '0 auto',
      }}
    >
      <InstitutionalLetterhead entidad={entidad} subtitle="Constancia de radicación" />
      <section style={{ display: 'grid', gridTemplateColumns: '1fr 160px', gap: 'var(--s-6)' }}>
        <div>
          <DataRow label="Número de radicado" value={radicado.numero_radicado} mono />
          <DataRow label="Fecha y hora" value={fmtFecha(radicado.fecha_radicacion)} />
          <DataRow label="Tipo" value={radicado.tipo_radicado || 'entrada'} />
          <DataRow label="Canal" value={radicado.canal_nombre || '—'} />
          <DataRow label="Asunto" value={radicado.asunto} />
          {radicado.estado && <DataRow label="Estado" value={radicado.estado} />}
        </div>
        <div style={{ textAlign: 'center' }}>
          <QrPlaceholder code={codigo} url={url} />
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            Verifique en
          </div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              wordBreak: 'break-all',
            }}
          >
            {url}
          </div>
          <div
            data-testid="codigo-verificacion"
            style={{
              marginTop: 'var(--s-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: '0.08em',
            }}
          >
            {codigo}
          </div>
        </div>
      </section>
      <footer style={{ marginTop: 'var(--s-6)', borderTop: '1px solid var(--border-subtle)', paddingTop: 'var(--s-4)', fontSize: 11.5, color: 'var(--fg-tertiary)' }}>
        Este documento es una constancia oficial generada por el sistema de
        gestión documental. Su autenticidad puede verificarse en línea con
        el código QR o el código alfanumérico arriba.
      </footer>
    </article>
  );
}

function DataRow({ label, value, mono = false }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '160px 1fr',
        gap: 'var(--s-3)',
        padding: '6px 0',
        borderBottom: '1px dashed var(--border-subtle)',
      }}
    >
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      <span style={{ fontFamily: mono ? 'var(--font-mono)' : undefined }}>
        {value || '—'}
      </span>
    </div>
  );
}

/**
 * QrPlaceholder — render mínimo determinista (no necesitamos un QR
 * decodificable en la UI mock; el backend ya genera la URL). Si el host
 * inyecta `window.qrcode`/lib, podríamos delegar. En este placeholder
 * mostramos un grid hash-based del código para visualizar dónde irá.
 */
function QrPlaceholder({ code, url }) {
  const cells = 17;
  const seed = hashCode(code + url);
  const bits = [];
  for (let i = 0; i < cells * cells; i++) {
    bits.push(((seed >> (i % 31)) ^ (i * 2654435761)) & 1);
  }
  const cellSize = 8;
  return (
    <svg
      role="img"
      aria-label={`Código QR para verificar el radicado ${code}`}
      width={cells * cellSize}
      height={cells * cellSize}
      viewBox={`0 0 ${cells * cellSize} ${cells * cellSize}`}
      data-testid="qr-placeholder"
      style={{ display: 'block', margin: '0 auto', border: '1px solid var(--border-default)' }}
    >
      <rect width="100%" height="100%" fill="white" />
      {bits.map((b, i) => (
        b ? (
          <rect
            key={i}
            x={(i % cells) * cellSize}
            y={Math.floor(i / cells) * cellSize}
            width={cellSize}
            height={cellSize}
            fill="black"
          />
        ) : null
      ))}
    </svg>
  );
}

function hashCode(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-CO', {
      year: 'numeric', month: 'long', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default RadicadoConstanciaPreview;
