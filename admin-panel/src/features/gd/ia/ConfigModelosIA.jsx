/**
 * ConfigModelosIA — GD-UI-0078. Configuración de modelos IA.
 *
 * Solo `gd.admin_sistema` RW. Lista modelos disponibles con:
 *  - codigo, nombre, proveedor (openai, anthropic, grok…)
 *  - activo (toggle)
 *  - temperatura (slider 0..1)
 *  - max_tokens
 *  - guardrails (lista de strings: 'no_pii', 'no_secrets', etc.)
 *  - usos_permitidos (sugerencia, resumen, búsqueda, asistente, pii)
 *
 * Cambios se aplican inmediato (con confirmación) y quedan en
 * audit log.
 */
import React, { useState, useEffect } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useConfigModelosIa, useActualizarConfigModelosIa,
} from './useGdIa.js';

const USOS = ['sugerencia', 'resumen', 'busqueda', 'asistente', 'pii'];

export function ConfigModelosIA({
  session, roles = [], ...shellProps
}) {
  const puedeEditar = gdCanAny(roles, 'IA-008', 'RW');
  const tienePermiso = puedeEditar || gdCanAny(roles, 'IA-008', 'R');
  const cfg = useConfigModelosIa(session);
  const act = useActualizarConfigModelosIa(session);
  const [edits, setEdits] = useState({});
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    if (cfg.data?.modelos) {
      const map = {};
      for (const m of cfg.data.modelos) {
        map[m.codigo] = {
          temperatura: m.temperatura ?? 0.7,
          max_tokens: m.max_tokens ?? 2048,
          activo: !!m.activo,
          guardrails: Array.isArray(m.guardrails) ? m.guardrails : [],
          usos_permitidos: Array.isArray(m.usos_permitidos) ? m.usos_permitidos : [],
        };
      }
      setEdits(map);
    }
  }, [cfg.data]);

  function actualizar(codigo, k, v) {
    setEdits((e) => ({
      ...e,
      [codigo]: { ...e[codigo], [k]: v },
    }));
  }

  function toggleUso(codigo, uso) {
    setEdits((e) => {
      const usos = new Set(e[codigo]?.usos_permitidos || []);
      if (usos.has(uso)) usos.delete(uso); else usos.add(uso);
      return { ...e, [codigo]: { ...e[codigo], usos_permitidos: [...usos] } };
    });
  }

  async function guardar(codigo) {
    setFeedback(null);
    try {
      await act.submit({ codigo, ...edits[codigo] });
      setFeedback({ ok: true, codigo });
      cfg.refresh?.();
    } catch (err) {
      setFeedback({ ok: false, codigo, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Configuración modelos IA' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Configuración de modelos IA</h1>
          <p className="subtitle">
            Modelos disponibles, parámetros (temperatura,
            max_tokens), guardrails de seguridad y mapeo a
            funcionalidades. Cambios quedan en auditoría.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={cfg.refresh}
            data-testid="ia-cfg-refresh"
          >Recargar</button>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="ia-cfg-no-perm"
        >
          <div className="body">
            Solo el administrador del sistema puede acceder.
          </div>
        </div>
      )}

      {cfg.loading && <p className="muted">Cargando modelos…</p>}
      {cfg.error && (
        <div className="alert danger" role="alert"
          data-testid="ia-cfg-error"
        >
          <div className="body">{cfg.error.message}</div>
        </div>
      )}

      {tienePermiso && cfg.data?.defaults && (
        <div className="card" style={{ padding: 'var(--s-3)',
          marginBottom: 'var(--s-3)' }}
          data-testid="ia-cfg-defaults"
        >
          <strong style={{ fontSize: 13 }}>Modelos por defecto</strong>
          <div style={{ display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 'var(--s-2)', marginTop: 'var(--s-2)' }}
          >
            {Object.entries(cfg.data.defaults).map(([k, v]) => (
              <div key={k} style={{ fontSize: 12 }}>
                <strong>{k}</strong>: <code>{v}</code>
              </div>
            ))}
          </div>
        </div>
      )}

      {tienePermiso && cfg.data?.modelos && cfg.data.modelos.map((m) => (
        <div key={m.codigo} className="card"
          style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-3)' }}
          data-testid="ia-cfg-modelo"
        >
          <div style={{ display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline' }}
          >
            <div>
              <h3 style={{ fontSize: 14, margin: 0 }}>
                {m.nombre || m.codigo}
                <small className="muted" style={{ marginLeft: 8 }}>
                  ({m.proveedor || '?'})
                </small>
              </h3>
              <code style={{ fontSize: 11, color: 'var(--c-muted)' }}>
                {m.codigo}
              </code>
            </div>
            {puedeEditar && (
              <label style={{ fontSize: 12 }}>
                <input type="checkbox"
                  checked={!!edits[m.codigo]?.activo}
                  onChange={(e) => actualizar(m.codigo, 'activo', e.target.checked)}
                  data-testid={`ia-cfg-activo-${m.codigo}`}
                />
                {' '}Activo
              </label>
            )}
          </div>

          {puedeEditar && edits[m.codigo] && (
            <div style={{ display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 'var(--s-3)', marginTop: 'var(--s-3)' }}
            >
              <label style={{ fontSize: 12 }}>
                Temperatura: {edits[m.codigo].temperatura.toFixed(2)}
                <input type="range" min="0" max="1" step="0.05"
                  value={edits[m.codigo].temperatura}
                  onChange={(e) => actualizar(m.codigo, 'temperatura',
                    parseFloat(e.target.value))}
                  style={{ width: '100%' }}
                  data-testid={`ia-cfg-temp-${m.codigo}`}
                />
              </label>
              <label style={{ fontSize: 12 }}>
                Max tokens
                <input type="number" min="128" max="32768" step="128"
                  value={edits[m.codigo].max_tokens}
                  onChange={(e) => actualizar(m.codigo, 'max_tokens',
                    parseInt(e.target.value, 10) || 2048)}
                  style={{ width: '100%' }}
                  data-testid={`ia-cfg-tokens-${m.codigo}`}
                />
              </label>
              <div style={{ fontSize: 12 }}>
                <strong>Guardrails</strong>
                <input type="text"
                  value={edits[m.codigo].guardrails.join(', ')}
                  onChange={(e) => actualizar(m.codigo, 'guardrails',
                    e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
                  placeholder="no_pii, no_secrets, no_violencia…"
                  style={{ width: '100%' }}
                  data-testid={`ia-cfg-guard-${m.codigo}`}
                />
              </div>
              <div style={{ fontSize: 12 }}>
                <strong>Usos permitidos</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap',
                  gap: 'var(--s-1)', marginTop: 'var(--s-1)' }}
                >
                  {USOS.map((u) => (
                    <label key={u} style={{ fontSize: 11 }}>
                      <input type="checkbox"
                        checked={edits[m.codigo].usos_permitidos.includes(u)}
                        onChange={() => toggleUso(m.codigo, u)}
                        data-testid={`ia-cfg-uso-${m.codigo}-${u}`}
                      />
                      {' '}{u}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {puedeEditar && (
            <div style={{ marginTop: 'var(--s-3)' }}>
              <button type="button" className="btn btn-primary btn-sm"
                onClick={() => guardar(m.codigo)}
                disabled={act.loading}
                data-testid={`ia-cfg-guardar-${m.codigo}`}
              >{act.loading && feedback?.codigo === m.codigo
                  ? 'Guardando…' : 'Guardar cambios'}</button>
            </div>
          )}

          {feedback && feedback.codigo === m.codigo && (
            <div className={`alert ${feedback.ok ? 'success' : 'danger'}`}
              role="status" style={{ marginTop: 'var(--s-2)' }}
              data-testid={`ia-cfg-feedback-${m.codigo}`}
            >
              <div className="body">
                {feedback.ok
                  ? 'Configuración guardada.'
                  : (feedback.error?.message || 'Error guardando.')}
              </div>
            </div>
          )}
        </div>
      ))}

      {tienePermiso && cfg.data?.modelos?.length === 0 && (
        <div className="empty" data-testid="ia-cfg-empty">
          <p className="muted">Sin modelos IA configurados.</p>
        </div>
      )}
    </GdShell>
  );
}

export default ConfigModelosIA;
