/**
 * InstitutionalLetterhead — encabezado oficial para constancias y reportes.
 *
 * RNF-014/040: las constancias y reportes oficiales deben llevar branding
 * institucional (logo + nombre + NIT) — NO el branding de CopilotoIA.
 *
 * Recibe `entidad` via prop o se cargará en el ancestro vía
 * `GET /api/v1/gd/entidad`. Aquí solo renderizamos.
 */
import React from 'react';

export function InstitutionalLetterhead({ entidad, subtitle }) {
  if (!entidad) {
    return (
      <header className="institutional-letterhead skeleton" data-testid="letterhead-skeleton">
        <p className="muted">Cargando datos institucionales…</p>
      </header>
    );
  }
  const {
    nombre_oficial,
    nit,
    direccion,
    telefono,
    correo_oficial,
    sitio_web,
    logo_url,
  } = entidad;
  return (
    <header
      className="institutional-letterhead"
      data-testid="institutional-letterhead"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--s-5)',
        padding: 'var(--s-5)',
        borderBottom: '2px solid var(--slate-900)',
        marginBottom: 'var(--s-6)',
      }}
    >
      {logo_url ? (
        <img
          src={logo_url}
          alt={`Logo ${nombre_oficial}`}
          style={{ height: 64, width: 'auto', flexShrink: 0 }}
        />
      ) : (
        <div
          className="mark"
          aria-hidden="true"
          style={{
            width: 64, height: 64, borderRadius: 'var(--r-md)',
            background: 'var(--slate-900)', color: 'white',
            display: 'grid', placeItems: 'center',
            fontFamily: 'var(--font-display)',
            fontWeight: 600, fontSize: 20,
          }}
        >
          {(nombre_oficial || 'GD').slice(0, 2).toUpperCase()}
        </div>
      )}
      <div style={{ flex: 1 }}>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 18, fontWeight: 700,
            lineHeight: 1.2, margin: 0,
          }}
        >
          {nombre_oficial}
        </h1>
        {nit && (
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            NIT: {nit}
          </div>
        )}
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          {[direccion, telefono, correo_oficial, sitio_web]
            .filter(Boolean)
            .join(' · ')}
        </div>
        {subtitle && (
          <div
            style={{
              marginTop: 'var(--s-3)',
              fontSize: 13.5,
              fontWeight: 600,
              color: 'var(--slate-800)',
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </header>
  );
}

export default InstitutionalLetterhead;
