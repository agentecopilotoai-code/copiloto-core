/**
 * ConfigCanalesEmail — GD-UI-0084.
 *
 * Solo `gd.admin_sistema` RW. CRUD de canales SMTP/IMAP/POP3:
 *  - host, port, usuario, password (write-only), tls
 *  - activo (toggle)
 *  - "Probar conexión" — backend hace AUTH + LIST básico.
 * Mostrar último_check + estado.
 *
 * NOTA seguridad: el backend NUNCA devuelve el password en GET.
 * El campo password en UI escribe nuevo valor; vacío = no cambia.
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useConfigCanalesEmail, useActualizarCanalEmail,
  useProbarCanalEmail,
} from './useGdCorreo.js';

export function ConfigCanalesEmail({
  session, roles = [], ...shellProps
}) {
  const puedeEditar = gdCanAny(roles, 'COR-EMAIL-004', 'RW');
  const tienePermiso = puedeEditar || gdCanAny(roles, 'COR-EMAIL-004', 'R');
  const cfg = useConfigCanalesEmail(session);
  const act = useActualizarCanalEmail(session);
  const probar = useProbarCanalEmail(session);
  const [edits, setEdits] = useState({});
  const [pwdEdit, setPwdEdit] = useState({});
  const [feedback, setFeedback] = useState(null);
  const [pruebaResultado, setPruebaResultado] = useState({});

  useEffect(() => {
    if (cfg.items?.length) {
      const map = {};
      for (const c of cfg.items) {
        map[c.id] = {
          host: c.host || '', port: c.port || 587,
          usuario: c.usuario || '', tls: !!c.tls,
          activo: !!c.activo,
        };
      }
      setEdits(map);
    }
  }, [cfg.items]);

  function actualizar(id, k, v) {
    setEdits((e) => ({
      ...e,
      [id]: { ...e[id], [k]: v },
    }));
  }

  async function guardar(id) {
    setFeedback(null);
    const payload = { ...edits[id] };
    // Solo enviar password si se escribió uno nuevo.
    if (pwdEdit[id]) payload.password = pwdEdit[id];
    try {
      await act.submit(id, payload);
      setFeedback({ ok: true, id });
      setPwdEdit((p) => ({ ...p, [id]: '' }));
      cfg.refresh();
    } catch (err) {
      setFeedback({ ok: false, id, error: err });
    }
  }

  async function probarConexion(id) {
    setPruebaResultado((p) => ({ ...p, [id]: { loading: true } }));
    try {
      const r = await probar.submit(id);
      setPruebaResultado((p) => ({ ...p, [id]: { ok: r?.ok, latencia: r?.latencia_ms } }));
    } catch (err) {
      setPruebaResultado((p) => ({ ...p, [id]: { ok: false, error: err.message } }));
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Canales de correo' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Configuración de canales de correo</h1>
          <p className="subtitle">
            Canales SMTP (envío) y IMAP/POP3 (recepción). Solo
            administradores del sistema pueden modificar. Cambios
            quedan en auditoría.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={cfg.refresh}
            data-testid="cor-cfg-refresh"
          >Recargar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="cor-cfg-no-perm"
        >
          <div className="body">
            Solo administradores pueden ver la configuración.
          </div>
        </div>
      )}

      {cfg.loading && <p className="muted">Cargando canales…</p>}
      {cfg.error && (
        <div className="alert danger" role="alert"
          data-testid="cor-cfg-error"
        >
          <div className="body">{cfg.error.message}</div>
        </div>
      )}

      {tienePermiso && cfg.items.map((c) => (
        <div key={c.id} className="card"
          style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-3)' }}
          data-testid="cor-cfg-canal"
        >
          <div style={{ display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline' }}
          >
            <div>
              <h3 style={{ fontSize: 14, margin: 0 }}>
                {c.nombre || c.id}
                <small className="muted" style={{ marginLeft: 8 }}>
                  ({c.tipo})
                </small>
              </h3>
              {c.ultimo_check && (
                <code style={{ fontSize: 11, color: 'var(--c-muted)' }}>
                  último check: {new Date(c.ultimo_check).toLocaleString('es-CO')}
                </code>
              )}
            </div>
            {puedeEditar && (
              <label style={{ fontSize: 12 }}>
                <input type="checkbox"
                  checked={!!edits[c.id]?.activo}
                  onChange={(e) => actualizar(c.id, 'activo', e.target.checked)}
                  data-testid={`cor-cfg-activo-${c.id}`}
                />
                {' '}Activo
              </label>
            )}
          </div>

          {puedeEditar && edits[c.id] && (
            <div style={{ display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 'var(--s-3)', marginTop: 'var(--s-3)' }}
            >
              <label style={{ fontSize: 12 }}>
                Host
                <input type="text" value={edits[c.id].host}
                  onChange={(e) => actualizar(c.id, 'host', e.target.value)}
                  style={{ width: '100%' }}
                  data-testid={`cor-cfg-host-${c.id}`}
                />
              </label>
              <label style={{ fontSize: 12 }}>
                Puerto
                <input type="number" value={edits[c.id].port}
                  onChange={(e) => actualizar(c.id, 'port',
                    parseInt(e.target.value, 10) || 587)}
                  style={{ width: '100%' }}
                  data-testid={`cor-cfg-port-${c.id}`}
                />
              </label>
              <label style={{ fontSize: 12 }}>
                Usuario
                <input type="text" value={edits[c.id].usuario}
                  onChange={(e) => actualizar(c.id, 'usuario', e.target.value)}
                  style={{ width: '100%' }}
                  data-testid={`cor-cfg-user-${c.id}`}
                />
              </label>
              <label style={{ fontSize: 12 }}>
                Password (dejar vacío para no cambiar)
                <input type="password" autoComplete="new-password"
                  value={pwdEdit[c.id] || ''}
                  onChange={(e) => setPwdEdit((p) => ({ ...p, [c.id]: e.target.value }))}
                  style={{ width: '100%' }}
                  data-testid={`cor-cfg-pwd-${c.id}`}
                />
              </label>
              <label style={{ fontSize: 12 }}>
                <input type="checkbox" checked={edits[c.id].tls}
                  onChange={(e) => actualizar(c.id, 'tls', e.target.checked)}
                  data-testid={`cor-cfg-tls-${c.id}`}
                />
                {' '}TLS
              </label>
            </div>
          )}

          {puedeEditar && (
            <div style={{ display: 'flex', gap: 'var(--s-2)',
              marginTop: 'var(--s-3)' }}
            >
              <button type="button" className="btn btn-primary btn-sm"
                onClick={() => guardar(c.id)}
                disabled={act.loading}
                data-testid={`cor-cfg-guardar-${c.id}`}
              >Guardar</button>
              <button type="button" className="btn btn-secondary btn-sm"
                onClick={() => probarConexion(c.id)}
                disabled={pruebaResultado[c.id]?.loading}
                data-testid={`cor-cfg-probar-${c.id}`}
              >{pruebaResultado[c.id]?.loading ? 'Probando…' : 'Probar conexión'}</button>
            </div>
          )}

          {pruebaResultado[c.id] && !pruebaResultado[c.id].loading && (
            <div className={`alert ${pruebaResultado[c.id].ok ? 'success' : 'danger'}`}
              role="status" style={{ marginTop: 'var(--s-2)' }}
              data-testid={`cor-cfg-prueba-${c.id}`}
            >
              <div className="body">
                {pruebaResultado[c.id].ok
                  ? `Conexión OK (${pruebaResultado[c.id].latencia} ms).`
                  : `Falló: ${pruebaResultado[c.id].error || 'error'}.`}
              </div>
            </div>
          )}

          {feedback && feedback.id === c.id && (
            <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
              role="status" style={{ marginTop: 'var(--s-2)' }}
              data-testid={`cor-cfg-feedback-${c.id}`}
            >
              <div className="body">
                {feedback.ok ? 'Configuración guardada.'
                  : (feedback.error?.message || 'Error guardando.')}
              </div>
            </div>
          )}
        </div>
      ))}

      {tienePermiso && cfg.items.length === 0 && !cfg.loading && (
        <div className="empty" data-testid="cor-cfg-empty">
          <p className="muted">Sin canales de correo configurados.</p>
        </div>
      )}
    </GdShell>
  );
}

export default ConfigCanalesEmail;
