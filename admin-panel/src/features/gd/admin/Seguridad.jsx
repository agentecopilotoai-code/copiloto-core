/**
 * Seguridad — GD-UI-0064/0065. Configuración de MFA, sesiones,
 * política de contraseñas y revocación de sesiones activas.
 *
 * Permisos: SEG-PWD, SEG-SES, SEG-MFA (admin seguridad). Toda
 * mutación queda registrada en audit trail con motivo.
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useConfigSeguridad, useActualizarConfigSeguridad,
  useSesionesActivas, useRevocarSesion,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TABS = ['Política', 'MFA', 'Sesiones activas'];

export function Seguridad({ session, roles = [], ...shellProps }) {
  const [tab, setTab] = useState('Política');
  const cfg = useConfigSeguridad(session);
  const puedePwd = gdCanAny(roles, 'SEG-PWD', 'RW');
  const puedeMfa = gdCanAny(roles, 'SEG-MFA', 'RW');
  const puedeSes = gdCanAny(roles, 'SEG-SES', 'R');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Seguridad' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Seguridad</h1>
          <p className="subtitle">
            Política de contraseñas, MFA y sesiones activas.
          </p>
        </div>
      </div>

      <nav className="tabs" data-testid="seg-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t} role="tab"
            aria-selected={tab === t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
            data-testid={`seg-tab-btn-${t}`}
          >{t}</button>
        ))}
      </nav>

      <div className="card" style={{ padding: 'var(--s-5)' }}>
        {tab === 'Política' && (
          <PoliticaPwd cfg={cfg} session={session} puedeEditar={puedePwd} />
        )}
        {tab === 'MFA' && (
          <ConfigMFA cfg={cfg} session={session} puedeEditar={puedeMfa} />
        )}
        {tab === 'Sesiones activas' && puedeSes && (
          <SesionesActivas session={session} roles={roles} />
        )}
        {tab === 'Sesiones activas' && !puedeSes && (
          <p className="muted" data-testid="seg-ses-no-perm">
            Sin permisos para ver sesiones activas.
          </p>
        )}
      </div>
    </GdShell>
  );
}

function PoliticaPwd({ cfg, session, puedeEditar }) {
  const editar = useActualizarConfigSeguridad(session);
  const [form, setForm] = useState({
    pwd_min_length: 12, pwd_require_upper: true,
    pwd_require_number: true, pwd_require_symbol: true,
    pwd_expira_dias: 90, sesion_timeout_min: 30,
  });
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);

  useEffect(() => {
    if (cfg.data) {
      setForm((p) => ({ ...p, ...cfg.data.password || {}, ...cfg.data.sesion || {} }));
    }
  }, [cfg.data]);

  async function handle() {
    try {
      await editar.submit({
        password: {
          pwd_min_length: Number(form.pwd_min_length),
          pwd_require_upper: form.pwd_require_upper,
          pwd_require_number: form.pwd_require_number,
          pwd_require_symbol: form.pwd_require_symbol,
          pwd_expira_dias: Number(form.pwd_expira_dias),
        },
        motivo,
      });
      cfg.refresh();
    } catch { /* hook */ }
  }

  if (cfg.loading) return <p className="muted">Cargando…</p>;
  if (cfg.error) return (
    <div className="alert danger" role="alert">
      <div className="body">{cfg.error.message || 'Error.'}</div>
    </div>
  );

  return (
    <div data-testid="seg-pol">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>Política de contraseñas</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="field">
          <label>Longitud mínima</label>
          <input type="number" className="input" min={8}
            disabled={!puedeEditar}
            value={form.pwd_min_length}
            onChange={(e) => setForm({ ...form, pwd_min_length: e.target.value })}
            data-testid="seg-pwd-min" />
        </div>
        <div className="field">
          <label>Expira en (días)</label>
          <input type="number" className="input"
            disabled={!puedeEditar}
            value={form.pwd_expira_dias}
            onChange={(e) => setForm({ ...form, pwd_expira_dias: e.target.value })}
            data-testid="seg-pwd-exp" />
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 'var(--s-3)' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input type="checkbox" checked={form.pwd_require_upper}
            disabled={!puedeEditar}
            onChange={(e) => setForm({ ...form, pwd_require_upper: e.target.checked })}
            data-testid="seg-pwd-upper" />
          Requerir mayúscula
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input type="checkbox" checked={form.pwd_require_number}
            disabled={!puedeEditar}
            onChange={(e) => setForm({ ...form, pwd_require_number: e.target.checked })}
            data-testid="seg-pwd-number" />
          Requerir número
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input type="checkbox" checked={form.pwd_require_symbol}
            disabled={!puedeEditar}
            onChange={(e) => setForm({ ...form, pwd_require_symbol: e.target.checked })}
            data-testid="seg-pwd-symbol" />
          Requerir símbolo
        </label>
      </div>
      {puedeEditar && (
        <div style={{ marginTop: 'var(--s-4)' }}>
          <JustificacionRequiredField
            value={motivo}
            onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
            label="Motivo del cambio"
            id="seg-pol-motivo"
          />
        </div>
      )}
      {editar.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{editar.error.message || 'Error.'}</div>
        </div>
      )}
      {puedeEditar && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-accent"
            disabled={!valid || editar.submitting} onClick={handle}
            data-testid="seg-pol-guardar"
          >{editar.submitting ? 'Guardando…' : 'Guardar política'}</button>
        </div>
      )}
    </div>
  );
}

function ConfigMFA({ cfg, session, puedeEditar }) {
  const editar = useActualizarConfigSeguridad(session);
  const [form, setForm] = useState({
    mfa_obligatorio: false,
    mfa_metodo: 'totp',
    mfa_grace_dias: 7,
  });
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);

  useEffect(() => {
    if (cfg.data?.mfa) setForm((p) => ({ ...p, ...cfg.data.mfa }));
  }, [cfg.data]);

  async function handle() {
    try {
      await editar.submit({
        mfa: {
          mfa_obligatorio: form.mfa_obligatorio,
          mfa_metodo: form.mfa_metodo,
          mfa_grace_dias: Number(form.mfa_grace_dias),
        },
        motivo,
      });
      cfg.refresh();
    } catch { /* hook */ }
  }

  return (
    <div data-testid="seg-mfa">
      <h3 style={{ fontSize: 14, marginTop: 0 }}>Autenticación multifactor</h3>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
        <input type="checkbox" checked={form.mfa_obligatorio}
          disabled={!puedeEditar}
          onChange={(e) => setForm({ ...form, mfa_obligatorio: e.target.checked })}
          data-testid="seg-mfa-obl" />
        Exigir MFA para todos los usuarios GD
      </label>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 'var(--s-3)' }}>
        <div className="field">
          <label>Método</label>
          <select className="select"
            disabled={!puedeEditar}
            value={form.mfa_metodo}
            onChange={(e) => setForm({ ...form, mfa_metodo: e.target.value })}
            data-testid="seg-mfa-metodo"
          >
            <option value="totp">TOTP (app autenticadora)</option>
            <option value="email">Código por correo</option>
            <option value="sms">Código por SMS</option>
          </select>
        </div>
        <div className="field">
          <label>Período de gracia (días)</label>
          <input type="number" className="input"
            disabled={!puedeEditar}
            value={form.mfa_grace_dias}
            onChange={(e) => setForm({ ...form, mfa_grace_dias: e.target.value })}
            data-testid="seg-mfa-grace" />
        </div>
      </div>
      {puedeEditar && (
        <div style={{ marginTop: 'var(--s-4)' }}>
          <JustificacionRequiredField
            value={motivo}
            onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
            label="Motivo del cambio"
            id="seg-mfa-motivo"
          />
        </div>
      )}
      {editar.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{editar.error.message || 'Error.'}</div>
        </div>
      )}
      {puedeEditar && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-accent"
            disabled={!valid || editar.submitting} onClick={handle}
            data-testid="seg-mfa-guardar"
          >{editar.submitting ? 'Guardando…' : 'Guardar MFA'}</button>
        </div>
      )}
    </div>
  );
}

function SesionesActivas({ session, roles }) {
  const ses = useSesionesActivas(session);
  const [revocar, setRevocar] = useState(null);
  const hook = useRevocarSesion(session);
  const puedeRevocar = gdCanAny(roles, 'SEG-SES', 'RW');

  async function handleRevocar(motivo) {
    if (!revocar) return;
    try {
      await hook.submit(revocar.id, motivo);
      setRevocar(null);
      ses.refresh();
    } catch { /* hook */ }
  }

  return (
    <div data-testid="seg-ses">
      {ses.loading && <p className="muted">Cargando sesiones…</p>}
      {ses.error && (
        <div className="alert danger" role="alert">
          <div className="body">{ses.error.message || 'Error.'}</div>
        </div>
      )}
      {!ses.loading && !ses.error && ses.items.length === 0 && (
        <div className="empty" data-testid="seg-ses-empty">
          <p>No hay sesiones activas.</p>
        </div>
      )}
      {ses.items.length > 0 && (
        <table className="data-table" data-testid="seg-ses-table">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>IP</th>
              <th>Dispositivo</th>
              <th>Iniciada</th>
              {puedeRevocar && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {ses.items.map((s) => (
              <tr key={s.id} data-testid="seg-ses-row">
                <td>{s.usuario_email || s.usuario_id}</td>
                <td>{s.ip}</td>
                <td className="muted" style={{ fontSize: 12 }}>
                  {s.user_agent ? `${s.user_agent.slice(0, 40)}…` : '—'}
                </td>
                <td>{s.iniciada_en}</td>
                {puedeRevocar && (
                  <td>
                    <button type="button" className="btn btn-danger btn-sm"
                      onClick={() => setRevocar(s)}
                      data-testid="seg-ses-revocar"
                    >Revocar</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {revocar && (
        <RevocarSesionModal
          sesion={revocar}
          onClose={() => setRevocar(null)}
          onConfirm={handleRevocar}
          submitting={hook.submitting}
          error={hook.error}
        />
      )}
    </div>
  );
}

function RevocarSesionModal({ sesion, onClose, onConfirm, submitting, error }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  return (
    <div
      role="dialog" aria-modal="true" data-testid="seg-ses-revocar-modal"
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 480, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Revocar sesión</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          La sesión de <strong>{sesion.usuario_email || sesion.usuario_id}</strong>{' '}
          ({sesion.ip}) será invalidada inmediatamente.
        </p>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Motivo de la revocación"
          id="seg-ses-revocar-motivo"
        />
        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn btn-danger-solid"
            disabled={!valid || submitting} onClick={() => onConfirm(motivo)}
            data-testid="seg-ses-revocar-submit"
          >{submitting ? 'Revocando…' : 'Revocar'}</button>
        </div>
      </div>
    </div>
  );
}

export default Seguridad;
