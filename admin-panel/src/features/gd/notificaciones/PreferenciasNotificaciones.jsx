/**
 * PreferenciasNotificaciones — GD-UI-0082.
 *
 * Centro de preferencias del usuario:
 *  - Canales globales: email, push, sms, in_app (toggles).
 *  - Por tipo de notificación: cada tipo puede sobrescribir
 *    cuáles canales recibe.
 *  - Resumen diario (toggle + hora).
 *  - "No molestar" (rango horario).
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  usePreferenciasNotif, useActualizarPreferenciasNotif,
} from './useGdNotif.js';

const CANALES_GLOBALES = [
  { key: 'in_app', label: 'In-app' },
  { key: 'email', label: 'Email' },
  { key: 'push', label: 'Push (móvil)' },
  { key: 'sms', label: 'SMS' },
];

export function PreferenciasNotificaciones({
  session, roles = [], ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'NOT-PREF', 'RW');
  const prefs = usePreferenciasNotif(session);
  const act = useActualizarPreferenciasNotif(session);
  const [draft, setDraft] = useState(null);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    if (prefs.data) {
      setDraft({
        canales: { in_app: true, email: true, push: false, sms: false,
          ...(prefs.data.canales || {}) },
        por_tipo: { ...(prefs.data.por_tipo || {}) },
        resumen_diario: prefs.data.resumen_diario ?? null,
        no_molestar: prefs.data.no_molestar ?? null,
      });
    }
  }, [prefs.data]);

  function actCanal(canal, valor) {
    setDraft((d) => ({
      ...d,
      canales: { ...d.canales, [canal]: valor },
    }));
  }

  function actPorTipo(tipo, canal, valor) {
    setDraft((d) => ({
      ...d,
      por_tipo: {
        ...d.por_tipo,
        [tipo]: { ...(d.por_tipo?.[tipo] || {}), [canal]: valor },
      },
    }));
  }

  function setNoMolestar(inicio, fin) {
    setDraft((d) => ({
      ...d,
      no_molestar: (inicio || fin) ? { inicio: inicio || '00:00', fin: fin || '00:00' } : null,
    }));
  }

  async function guardar() {
    setFeedback(null);
    try {
      await act.submit(draft);
      setFeedback({ ok: true });
      prefs.refresh();
    } catch (err) {
      setFeedback({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Preferencias notificaciones' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Preferencias de notificaciones</h1>
          <p className="subtitle">
            Elige por qué canales recibes cada tipo de notificación.
            La configuración por tipo sobreescribe la global.
          </p>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="not-pref-no-perm"
        >
          <div className="body">No tienes permiso para editar preferencias.</div>
        </div>
      )}

      {prefs.loading && <p className="muted">Cargando…</p>}
      {prefs.error && (
        <div className="alert danger" role="alert"
          data-testid="not-pref-error"
        >
          <div className="body">{prefs.error.message}</div>
        </div>
      )}

      {tienePermiso && draft && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)',
            marginBottom: 'var(--s-3)' }}
            data-testid="not-pref-canales"
          >
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Canales globales</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap',
              gap: 'var(--s-3)' }}
            >
              {CANALES_GLOBALES.map((c) => (
                <label key={c.key} style={{ fontSize: 13 }}>
                  <input type="checkbox"
                    checked={!!draft.canales[c.key]}
                    onChange={(e) => actCanal(c.key, e.target.checked)}
                    data-testid={`not-pref-canal-${c.key}`}
                  />
                  {' '}{c.label}
                </label>
              ))}
            </div>
          </div>

          {Object.keys(draft.por_tipo || {}).length > 0 && (
            <div className="card" style={{ padding: 'var(--s-4)',
              marginBottom: 'var(--s-3)' }}
              data-testid="not-pref-tipos"
            >
              <h3 style={{ fontSize: 14, marginTop: 0 }}>
                Por tipo de notificación
              </h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Tipo</th>
                    {CANALES_GLOBALES.map((c) => (
                      <th key={c.key}>{c.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(draft.por_tipo).map(([tipo, cfg]) => (
                    <tr key={tipo} data-testid="not-pref-tipo-row">
                      <td>{tipo}</td>
                      {CANALES_GLOBALES.map((c) => (
                        <td key={c.key}>
                          <input type="checkbox"
                            checked={!!cfg?.[c.key]}
                            onChange={(e) => actPorTipo(tipo, c.key, e.target.checked)}
                            data-testid={`not-pref-tipo-${tipo}-${c.key}`}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="card" style={{ padding: 'var(--s-4)',
            marginBottom: 'var(--s-3)' }}
            data-testid="not-pref-no-molestar"
          >
            <h3 style={{ fontSize: 14, marginTop: 0 }}>No molestar</h3>
            <div style={{ display: 'flex', gap: 'var(--s-2)',
              alignItems: 'center' }}
            >
              <label style={{ fontSize: 13 }}>
                Desde{' '}
                <input type="time"
                  value={draft.no_molestar?.inicio || ''}
                  onChange={(e) => setNoMolestar(e.target.value, draft.no_molestar?.fin)}
                  data-testid="not-pref-nm-inicio"
                />
              </label>
              <label style={{ fontSize: 13 }}>
                Hasta{' '}
                <input type="time"
                  value={draft.no_molestar?.fin || ''}
                  onChange={(e) => setNoMolestar(draft.no_molestar?.inicio, e.target.value)}
                  data-testid="not-pref-nm-fin"
                />
              </label>
              {draft.no_molestar && (
                <button type="button" className="btn btn-sm"
                  onClick={() => setDraft((d) => ({ ...d, no_molestar: null }))}
                  data-testid="not-pref-nm-clear"
                >Quitar</button>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--s-2)',
            justifyContent: 'flex-end' }}
          >
            <button type="button" className="btn btn-primary"
              onClick={guardar} disabled={act.loading}
              data-testid="not-pref-guardar"
            >{act.loading ? 'Guardando…' : 'Guardar preferencias'}</button>
          </div>

          {feedback && (
            <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
              role="status" style={{ marginTop: 'var(--s-3)' }}
              data-testid="not-pref-feedback"
            >
              <div className="body">
                {feedback.ok ? 'Preferencias guardadas.'
                  : (feedback.error?.message || 'Error guardando.')}
              </div>
            </div>
          )}
        </>
      )}
    </GdShell>
  );
}

export default PreferenciasNotificaciones;
