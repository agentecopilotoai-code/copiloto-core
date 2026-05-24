/**
 * EvidenciaFirma — GD-UI-0043. Detalle de evidencia técnica de la firma.
 *
 * Muestra hash documental, IP, fecha, geolocalización aproximada,
 * detalles del certificado (si aplica) y método de firma (digital /
 * escaneada). Permite descargar evidencia consolidada.
 */
import React from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useEvidenciaFirma } from './useGdFirmas.js';

export function EvidenciaFirma({
  session,
  firmaId,
  onNavigate: _onNavigate,
  ...shellProps
}) {
  const { data, loading, error } = useEvidenciaFirma(session, firmaId);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Firmas', path: '/gd/firmas' },
        { label: 'Evidencia' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Evidencia de firma</h1>
          <p className="subtitle">
            Trazabilidad técnica de la firma electrónica registrada.
          </p>
        </div>
      </div>

      {loading && <p className="muted">Cargando evidencia…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error al cargar.'}</div>
        </div>
      )}

      {data && (
        <div className="card" style={{ padding: 'var(--s-5)' }} data-testid="evidencia-card">
          <h2 style={{ fontSize: 16, marginTop: 0 }}>Datos generales</h2>
          <Row label="Documento" value={data.documento_titulo || data.documento_id} />
          <Row label="Firmante" value={data.firmante_nombre || '—'} />
          <Row label="Cargo" value={data.firmante_cargo || '—'} />
          <Row label="Método" value={fmtMetodo(data.metodo)} />
          <Row label="Fecha de firma" value={fmtFecha(data.firmado_en)} />

          <h3 style={{ fontSize: 14, marginTop: 'var(--s-4)' }}>Evidencia técnica</h3>
          <Row label="Hash documento (SHA-256)" value={<code data-testid="evidencia-hash">{data.hash_documento || '—'}</code>} />
          <Row label="Dirección IP" value={data.ip || '—'} />
          <Row label="Geolocalización" value={fmtGeo(data.geolocalizacion)} />
          <Row label="Navegador / dispositivo" value={data.user_agent || '—'} />

          {data.certificado && (
            <>
              <h3 style={{ fontSize: 14, marginTop: 'var(--s-4)' }}>Certificado</h3>
              <Row label="Emisor" value={data.certificado.emisor || '—'} />
              <Row label="Serial" value={data.certificado.serial || '—'} />
              <Row label="Válido desde" value={fmtFecha(data.certificado.valido_desde)} />
              <Row label="Válido hasta" value={fmtFecha(data.certificado.valido_hasta)} />
              <Row label="Algoritmo" value={data.certificado.algoritmo || '—'} />
            </>
          )}

          {data.url_descarga_evidencia && (
            <div style={{ marginTop: 'var(--s-4)' }}>
              <a
                className="btn btn-accent"
                href={data.url_descarga_evidencia}
                download
                data-testid="evidencia-descargar"
              >Descargar evidencia consolidada</a>
            </div>
          )}
        </div>
      )}
    </GdShell>
  );
}

function Row({ label, value }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '220px 1fr',
      padding: '6px 0', borderBottom: '1px dashed var(--border-subtle)',
      fontSize: 14,
    }}>
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      <span>{value}</span>
    </div>
  );
}

function fmtMetodo(m) {
  if (m === 'digital') return 'Firma digital';
  if (m === 'escaneada') return 'Firma escaneada';
  if (m === 'manuscrita') return 'Firma manuscrita';
  return m || '—';
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-CO');
  } catch { return iso; }
}

function fmtGeo(g) {
  if (!g) return '—';
  if (typeof g === 'string') return g;
  if (g.ciudad || g.pais) {
    return [g.ciudad, g.region, g.pais].filter(Boolean).join(', ');
  }
  if (g.lat != null && g.lon != null) {
    return `${g.lat.toFixed?.(4) ?? g.lat}, ${g.lon.toFixed?.(4) ?? g.lon}`;
  }
  return '—';
}

export default EvidenciaFirma;
