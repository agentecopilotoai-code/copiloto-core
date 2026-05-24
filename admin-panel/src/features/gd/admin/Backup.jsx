/**
 * Backup — GD-UI-0062. Consulta de estado de backups + disparo manual.
 *
 * Permisos: BAK-001 (R). El disparo manual requiere admin_sistema RW
 * (lo valida backend). Integridad RNF-009: cada backup se sella con
 * hash + timestamp.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useEstadoBackups, useDispararBackupManual,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function Backup({ session, roles = [], ...shellProps }) {
  const { data, loading, error, refresh } = useEstadoBackups(session);
  const [showManual, setShowManual] = useState(false);
  const puedeDisparar = gdCanAny(roles, 'BAK-001', 'R'); // backend valida RW
  const backups = data?.items || data?.backups || (Array.isArray(data) ? data : []);

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Backup' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Backup y restauración</h1>
          <p className="subtitle">
            Estado de los backups automáticos + disparo manual de backup
            completo (registrado en auditoría).
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="bak-refresh"
          >Actualizar</button>
          {puedeDisparar && (
            <button type="button" className="btn btn-accent"
              onClick={() => setShowManual(true)}
              data-testid="bak-manual"
            >Backup manual</button>
          )}
        </div>
      </div>

      {data?.proximo_backup && (
        <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
          <p style={{ margin: 0, fontSize: 13 }} data-testid="bak-proximo">
            Próximo backup programado: <strong>{data.proximo_backup}</strong>{' '}
            ({data.frecuencia || 'diario'}).
          </p>
        </div>
      )}

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && backups.length === 0 && (
        <div className="empty" data-testid="bak-empty">
          <p>No hay backups registrados.</p>
        </div>
      )}
      {backups.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="data-table" data-testid="bak-table">
            <thead>
              <tr>
                <th>Inicio</th>
                <th>Tipo</th>
                <th>Estado</th>
                <th>Tamaño</th>
                <th>Hash (SHA-256)</th>
                <th>Duración</th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.id} data-testid="bak-row">
                  <td>{b.iniciado_en}</td>
                  <td><span className="badge">{b.tipo || 'auto'}</span></td>
                  <td>
                    <span className={`badge ${badgeTone(b.estado)}`}>{b.estado}</span>
                  </td>
                  <td className="num">{b.tamano_mb ? `${b.tamano_mb} MB` : '—'}</td>
                  <td><code style={{ fontSize: 11 }}>{b.hash?.slice(0, 16) || '—'}</code></td>
                  <td className="num">{b.duracion_seg ? `${b.duracion_seg}s` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showManual && (
        <BackupManualModal
          session={session}
          onClose={() => setShowManual(false)}
          onSuccess={() => { setShowManual(false); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function BackupManualModal({ session, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useDispararBackupManual(session);

  async function handle() {
    try {
      await hook.submit(motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="bak-manual-modal"
      style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)', display: 'grid', placeItems: 'center', zIndex: 50 }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 480, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Disparar backup manual</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Se ejecutará un backup completo del módulo. La operación queda
          registrada en auditoría con el motivo capturado.
        </p>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Motivo del backup manual"
          id="bak-manual-motivo"
        />
        {hook.error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{hook.error.message || 'Error.'}</div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button type="button" className="btn btn-accent"
            disabled={!valid || hook.submitting} onClick={handle}
            data-testid="bak-manual-submit"
          >{hook.submitting ? 'Encolando…' : 'Disparar backup'}</button>
        </div>
      </div>
    </div>
  );
}

function badgeTone(estado) {
  if (estado === 'exitoso' || estado === 'completado') return 'ok';
  if (estado === 'fallido' || estado === 'error') return 'danger';
  if (estado === 'en_progreso') return 'info';
  return 'neutral';
}

export default Backup;
