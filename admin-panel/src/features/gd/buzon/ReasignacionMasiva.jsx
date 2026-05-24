/**
 * ReasignacionMasiva — GD-UI-0019.
 *
 * Wizard que se dispara cuando un Admin Sistema inactiva un usuario que
 * tiene tareas pendientes. Permite reasignar las tareas en lote a otros
 * funcionarios — el backend lo enforce vía GD-API-0039.
 *
 * Flujo:
 *  1. Mostrar tareas pendientes del usuario inactivado.
 *  2. Para cada tarea, elegir nuevo responsable (UsuarioPicker).
 *  3. Justificación global obligatoria.
 *  4. Confirmar — submit en lote.
 */
import React, { useState, useMemo } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import { UsuarioPicker } from './UsuarioPicker.jsx';
import {
  useTareasPendientesUsuario,
  useReasignarTareasLote,
} from './useGdBuzon.js';

export function ReasignacionMasiva({
  session,
  userId,
  usuarioNombre,
  dependenciaId,
  onSuccess,
  onCancel,
  ...shellProps
}) {
  const { items, loading, error } = useTareasPendientesUsuario(session, userId);
  const reasigna = useReasignarTareasLote(session);

  // Map tareaId → nuevo_responsable_user_id
  const [asignaciones, setAsignaciones] = useState({});
  const [justif, setJustif] = useState('');
  const [justifValid, setJustifValid] = useState(false);

  function setNuevoResponsable(tareaId, userId) {
    setAsignaciones((p) => ({ ...p, [tareaId]: userId }));
  }

  const todasAsignadas = useMemo(() => {
    if (items.length === 0) return false;
    return items.every((t) => Boolean(asignaciones[t.id]));
  }, [items, asignaciones]);

  const canSubmit = todasAsignadas && justifValid && !reasigna.submitting;

  async function handleSubmit() {
    try {
      await reasigna.submit(userId, {
        tareas: items.map((t) => ({
          id: t.id,
          nuevo_responsable_user_id: asignaciones[t.id],
        })),
        justificacion: justif,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Administración', path: '/gd/admin/usuarios' },
        { label: 'Reasignación masiva' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Reasignar tareas pendientes</h1>
          <p className="subtitle">
            Reasignación obligatoria de las tareas de
            {' '}
            <strong>{usuarioNombre || `usuario ${userId}`}</strong>{' '}
            antes de inactivarlo.
          </p>
        </div>
      </div>

      {loading && <p className="muted">Cargando tareas pendientes…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error al cargar.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="reasig-empty">
          <p>
            Este usuario no tiene tareas pendientes. Puede proceder a
            inactivarlo sin reasignación.
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCancel}
            style={{ marginTop: 'var(--s-3)' }}
          >
            Cerrar
          </button>
        </div>
      )}

      {items.length > 0 && (
        <>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="data-table" data-testid="reasig-table">
              <thead>
                <tr>
                  <th>Tarea</th>
                  <th>Tipo</th>
                  <th>Vence</th>
                  <th>Nuevo responsable</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id} data-testid="reasig-row">
                    <td>
                      <div style={{ fontWeight: 600 }}>{t.titulo}</div>
                      <div className="muted" style={{ fontSize: 12 }}>{t.entidad_relacionada_titulo || ''}</div>
                    </td>
                    <td>{t.tipo}</td>
                    <td>{fmtFecha(t.vence_en)}</td>
                    <td style={{ minWidth: 240 }}>
                      <UsuarioPicker
                        session={session}
                        dependenciaId={t.dependencia_id || dependenciaId}
                        rol={t.rol_compatible}
                        value={asignaciones[t.id] || ''}
                        onChange={(v) => setNuevoResponsable(t.id, v)}
                        label=""
                        excluir={[userId]}
                        testId={`reasig-picker-${t.id}`}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card" style={{ padding: 'var(--s-5)', marginTop: 'var(--s-4)' }}>
            <JustificacionRequiredField
              value={justif}
              onChange={(v, ok) => { setJustif(v); setJustifValid(ok); }}
              label="Justificación global"
              id="justif-reasig"
              hint="Quedará registrada en la trazabilidad de cada tarea reasignada."
            />
            {reasigna.error && (
              <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
                <div className="body">{reasigna.error.message || 'Error al reasignar.'}</div>
              </div>
            )}
            {reasigna.result && (
              <div className="alert success" role="status" style={{ marginTop: 12 }}>
                <div className="body">
                  Reasignación exitosa. {items.length} tarea(s) actualizadas.
                </div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={onCancel}
                data-testid="reasig-cancelar"
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={!canSubmit}
                data-testid="reasig-submit"
              >
                {reasigna.submitting ? 'Reasignando…' : `Reasignar ${items.length} tarea(s)`}
              </button>
            </div>
            {!todasAsignadas && (
              <p className="hint" style={{ color: 'var(--amber-700)' }}>
                Debe asignar un responsable a cada tarea antes de continuar.
              </p>
            )}
          </div>
        </>
      )}
    </GdShell>
  );
}

function fmtFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('es-CO', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  } catch { return iso; }
}

export default ReasignacionMasiva;
