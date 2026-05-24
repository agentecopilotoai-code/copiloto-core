/**
 * VerificarConstanciaPublica — pantalla SIN AUTH para `/gd/verificar/{codigo}`.
 *
 * Consume GD-API-0030 (endpoint público). NUNCA muestra datos del solicitante
 * ni cuerpo del trámite — solo lo mínimo necesario para confirmar
 * autenticidad: número, fecha, estado, asunto resumido, dependencia
 * actual pública.
 *
 * Reusable también desde la app móvil del ciudadano (mismo endpoint).
 */
import React, { useEffect, useState } from 'react';

import { verificarConstanciaPublica } from '../services/gdApi.js';
import '../styles/portal.css';

export function VerificarConstanciaPublica({
  codigo,
  entidad,
  fetchFn,
}) {
  const [state, setState] = useState({ data: null, loading: true, error: null });

  useEffect(() => {
    if (!codigo) {
      setState({ data: null, loading: false, error: new Error('Código vacío.') });
      return;
    }
    let cancelled = false;
    const fn = fetchFn || verificarConstanciaPublica;
    fn(codigo)
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled) setState({ data: null, loading: false, error: err });
      });
    return () => { cancelled = true; };
  }, [codigo, fetchFn]);

  const { data, loading, error } = state;

  return (
    <div
      className="gd-shell-root"
      data-testid="verificar-publica-root"
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--s-6)',
      }}
    >
      <article
        className="card"
        style={{
          maxWidth: 560,
          width: '100%',
          padding: 'var(--s-6)',
        }}
      >
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            margin: 0,
            marginBottom: 'var(--s-2)',
          }}
        >
          Verificación de radicado
        </h1>
        <p className="muted" style={{ fontSize: 13 }}>
          Esta verificación confirma que el código corresponde a un
          radicado oficial del sistema. No expone información personal
          ni el contenido del trámite.
        </p>

        {loading && (
          <p className="muted" data-testid="verificar-loading">
            Consultando…
          </p>
        )}

        {error && (
          <div className="alert danger" role="alert" data-testid="verificar-error">
            <div className="body">
              <div className="title">Código no encontrado.</div>
              <div>
                El código <code>{codigo}</code> no corresponde a un
                radicado vigente. Verifique e intente nuevamente.
              </div>
            </div>
          </div>
        )}

        {data && (
          <div data-testid="verificar-result">
            {entidad && (
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--fg-tertiary)',
                  marginBottom: 'var(--s-4)',
                }}
              >
                Entidad: <strong>{entidad.nombre_oficial}</strong>
                {entidad.nit && ` · NIT ${entidad.nit}`}
              </div>
            )}
            <Row label="Número de radicado" value={data.numero_radicado} mono />
            <Row label="Fecha y hora" value={fmtFecha(data.fecha_radicacion)} />
            <Row label="Tipo" value={data.tipo_radicado || 'entrada'} />
            <Row label="Estado actual" value={data.estado_actual || data.estado} />
            <Row label="Asunto" value={data.asunto_resumido || data.asunto} />
            {data.dependencia_actual_publica && (
              <Row
                label="Dependencia actual"
                value={data.dependencia_actual_publica}
              />
            )}
            <div className="alert success" style={{ marginTop: 'var(--s-4)' }}>
              <div className="body">
                <div className="title">Documento auténtico.</div>
                <div>
                  El radicado existe en el sistema y se encuentra vigente.
                </div>
              </div>
            </div>
          </div>
        )}
      </article>
    </div>
  );
}

function Row({ label, value, mono = false }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '160px 1fr',
        padding: '8px 0',
        borderBottom: '1px dashed var(--border-subtle)',
        fontSize: 14,
      }}
    >
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      <span style={{ fontFamily: mono ? 'var(--font-mono)' : undefined }}>
        {value || '—'}
      </span>
    </div>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-CO', {
      year: 'numeric', month: 'long', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export default VerificarConstanciaPublica;
