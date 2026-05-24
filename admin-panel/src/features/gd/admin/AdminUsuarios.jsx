/**
 * AdminUsuarios — GD-UI-0052/0053/0054. Administración de usuarios GD.
 *
 * Lista filtrable + alta/edición + asignación/remoción de roles GD +
 * inactivación/reactivación con motivo (USR-001/002/004/005/007/011/012).
 *
 * Seguridad: separation-of-duties (RNF-058) — el creador del usuario
 * NO puede aprobarlo. La UI no asume gate aquí; el backend valida.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useUsuariosGd, useUsuarioGd,
  useCrearUsuarioGd, useActualizarUsuarioGd,
  useAsignarRolUsuarioGd, useRemoverRolUsuarioGd,
  useInactivarUsuarioGd, useReactivarUsuarioGd,
} from './useGdAdmin.js';
import { gdCanAny, GD_ROLES } from '../../../permissions/gd-matrix.js';

const ESTADOS = ['', 'activo', 'inactivo'];

export function AdminUsuarios({ session, roles = [], ...shellProps }) {
  const [filtros, setFiltros] = useState({});
  const [seleccionado, setSeleccionado] = useState(null);
  const [modal, setModal] = useState(null);
  const { items, total, loading, error, refresh } =
    useUsuariosGd(session, filtros);
  const puedeAdmin = gdCanAny(roles, 'USR-001', 'RW');

  function update(k, v) { setFiltros((p) => ({ ...p, [k]: v || undefined })); }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Administración de usuarios' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Administración de usuarios GD</h1>
          <p className="subtitle">
            {total} usuario(s) registrado(s) en el módulo de Gestión Documental.
          </p>
        </div>
        <div className="actions">
          <button
            type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="usr-refresh"
          >Actualizar</button>
          {puedeAdmin && (
            <button
              type="button" className="btn btn-accent"
              onClick={() => { setSeleccionado(null); setModal('nuevo'); }}
              data-testid="usr-nuevo"
            >+ Nuevo usuario</button>
          )}
        </div>
      </div>

      {!puedeAdmin && (
        <div className="alert warning" role="alert" data-testid="usr-no-perm">
          <div className="body">No tiene permisos para administrar usuarios.</div>
        </div>
      )}

      {puedeAdmin && (
        <>
          <div className="card" style={{ padding: 'var(--s-4)', marginBottom: 'var(--s-4)' }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 'var(--s-3)',
            }}>
              <div className="field">
                <label>Búsqueda</label>
                <input
                  type="search" className="input"
                  value={filtros.q || ''}
                  onChange={(e) => update('q', e.target.value)}
                  placeholder="Nombre o correo…"
                  data-testid="usr-filter-q"
                />
              </div>
              <div className="field">
                <label>Rol</label>
                <select
                  className="select"
                  value={filtros.rol || ''}
                  onChange={(e) => update('rol', e.target.value)}
                  data-testid="usr-filter-rol"
                >
                  <option value="">Todos</option>
                  {GD_ROLES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Estado</label>
                <select
                  className="select"
                  value={filtros.estado || ''}
                  onChange={(e) => update('estado', e.target.value)}
                  data-testid="usr-filter-estado"
                >
                  {ESTADOS.map((e) => (
                    <option key={e || 'all'} value={e}>{e || 'Todos'}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
            {error && (
              <div className="alert danger" role="alert" style={{ margin: 'var(--s-4)' }}>
                <div className="body">{error.message || 'Error.'}</div>
              </div>
            )}
            {!loading && !error && items.length === 0 && (
              <div className="empty" data-testid="usr-empty" style={{ margin: 'var(--s-4)' }}>
                <p>Sin usuarios con esos criterios.</p>
              </div>
            )}
            {items.length > 0 && (
              <table className="data-table" data-testid="usr-table">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Correo</th>
                    <th>Dependencia</th>
                    <th>Roles GD</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((u) => (
                    <tr key={u.id} data-testid="usr-row">
                      <td>{u.nombre_completo}</td>
                      <td className="muted" style={{ fontSize: 12 }}>{u.email}</td>
                      <td>{u.dependencia_nombre || '—'}</td>
                      <td>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {(u.roles || []).map((r) => (
                            <span key={r} className="badge" style={{ fontSize: 11 }}>
                              {r.replace('gd.', '')}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${u.estado === 'activo' ? 'ok' : 'neutral'}`}>
                          {u.estado}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            type="button" className="btn btn-secondary btn-sm"
                            onClick={() => { setSeleccionado(u); setModal('editar'); }}
                            data-testid="usr-editar"
                          >Editar</button>
                          <button
                            type="button" className="btn btn-secondary btn-sm"
                            onClick={() => { setSeleccionado(u); setModal('roles'); }}
                            data-testid="usr-roles"
                          >Roles</button>
                          {u.estado === 'activo' ? (
                            <button
                              type="button" className="btn btn-danger btn-sm"
                              onClick={() => { setSeleccionado(u); setModal('inactivar'); }}
                              data-testid="usr-inactivar"
                            >Inactivar</button>
                          ) : (
                            <button
                              type="button" className="btn btn-accent btn-sm"
                              onClick={() => { setSeleccionado(u); setModal('reactivar'); }}
                              data-testid="usr-reactivar"
                            >Reactivar</button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {modal === 'nuevo' && (
        <FormUsuarioModal
          session={session}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal === 'editar' && seleccionado && (
        <FormUsuarioModal
          session={session}
          usuario={seleccionado}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal === 'roles' && seleccionado && (
        <GestionRolesModal
          session={session}
          usuario={seleccionado}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal === 'inactivar' && seleccionado && (
        <InactivarUsuarioModal
          session={session}
          usuario={seleccionado}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal === 'reactivar' && seleccionado && (
        <ReactivarUsuarioModal
          session={session}
          usuario={seleccionado}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function FormUsuarioModal({ session, usuario, onClose, onSuccess }) {
  const isEdit = Boolean(usuario);
  const [form, setForm] = useState({
    nombre_completo: usuario?.nombre_completo || '',
    email: usuario?.email || '',
    dependencia_id: usuario?.dependencia_id || '',
    documento_identidad: usuario?.documento_identidad || '',
  });
  const crear = useCrearUsuarioGd(session);
  const editar = useActualizarUsuarioGd(session);
  const hook = isEdit ? editar : crear;

  async function handle() {
    try {
      if (isEdit) await editar.submit(usuario.id, form);
      else await crear.submit(form);
      onSuccess?.();
    } catch { /* hook */ }
  }

  const valid =
    form.nombre_completo.trim().length >= 3 &&
    /\S+@\S+\.\S+/.test(form.email);

  return (
    <ModalShell title={isEdit ? 'Editar usuario' : 'Nuevo usuario GD'} onClose={onClose} testid="usr-form-modal">
      <div className="field">
        <label>Nombre completo <span className="req">*</span></label>
        <input
          className="input"
          value={form.nombre_completo}
          onChange={(e) => setForm({ ...form, nombre_completo: e.target.value })}
          data-testid="usr-form-nombre"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Correo institucional <span className="req">*</span></label>
        <input
          type="email" className="input"
          value={form.email}
          disabled={isEdit}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          data-testid="usr-form-email"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Documento de identidad</label>
        <input
          className="input"
          value={form.documento_identidad}
          onChange={(e) => setForm({ ...form, documento_identidad: e.target.value })}
          data-testid="usr-form-doc"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>ID Dependencia</label>
        <input
          className="input"
          value={form.dependencia_id}
          onChange={(e) => setForm({ ...form, dependencia_id: e.target.value })}
          data-testid="usr-form-dep"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="usr-form-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function GestionRolesModal({ session, usuario, onClose, onSuccess }) {
  const ficha = useUsuarioGd(session, usuario.id);
  const [rolNuevo, setRolNuevo] = useState(GD_ROLES[0]);
  const [scope, setScope] = useState('global');
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const asignar = useAsignarRolUsuarioGd(session);
  const remover = useRemoverRolUsuarioGd(session);

  async function handleAsignar() {
    try {
      await asignar.submit(usuario.id, {
        rol: rolNuevo,
        scope_tipo: scope,
        motivo,
      });
      ficha.refresh();
      onSuccess?.();
    } catch { /* hook */ }
  }

  async function handleRemover(rol) {
    try {
      await remover.submit(usuario.id, rol, motivo || 'cambio de funciones');
      ficha.refresh();
      onSuccess?.();
    } catch { /* hook */ }
  }

  const rolesActuales = ficha.data?.roles || usuario.roles || [];

  return (
    <ModalShell title={`Roles de ${usuario.nombre_completo}`} onClose={onClose} testid="usr-roles-modal">
      <div data-testid="usr-roles-actuales" style={{ marginBottom: 'var(--s-3)' }}>
        <div className="muted" style={{ fontSize: 12 }}>Roles actuales</div>
        {rolesActuales.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>Sin roles GD.</p>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {rolesActuales.map((r) => (
              <li key={r} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', borderBottom: '1px dashed var(--border-subtle)' }}>
                <span style={{ fontSize: 13 }}>{r}</span>
                <button
                  type="button" className="btn btn-danger btn-sm"
                  onClick={() => handleRemover(r)}
                  disabled={remover.submitting}
                  data-testid="usr-rol-remover"
                >Remover</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <h3 style={{ fontSize: 14, marginTop: 'var(--s-4)' }}>Asignar nuevo rol</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="field">
          <label>Rol</label>
          <select className="select"
            value={rolNuevo}
            onChange={(e) => setRolNuevo(e.target.value)}
            data-testid="usr-rol-nuevo"
          >
            {GD_ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Alcance</label>
          <select className="select"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            data-testid="usr-rol-scope"
          >
            <option value="global">Global</option>
            <option value="dependencia">Dependencia</option>
          </select>
        </div>
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
          label="Motivo de la asignación / cambio"
          id="usr-rol-motivo"
        />
      </div>
      {(asignar.error || remover.error) && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">
            {(asignar.error || remover.error).message || 'Error.'}
          </div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-accent"
          disabled={!motivoValid || asignar.submitting} onClick={handleAsignar}
          data-testid="usr-rol-asignar"
        >{asignar.submitting ? 'Asignando…' : 'Asignar rol'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function InactivarUsuarioModal({ session, usuario, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarUsuarioGd(session);

  async function handle() {
    try {
      await hook.submit(usuario.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Inactivar usuario" onClose={onClose} testid="usr-inactivar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        <strong>{usuario.nombre_completo}</strong> dejará de poder acceder
        al módulo de Gestión Documental. Las tareas asignadas deben
        reasignarse antes de inactivar.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="usr-inactivar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="usr-inactivar-submit"
        >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ReactivarUsuarioModal({ session, usuario, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useReactivarUsuarioGd(session);

  async function handle() {
    try {
      await hook.submit(usuario.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Reactivar usuario" onClose={onClose} testid="usr-reactivar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        <strong>{usuario.nombre_completo}</strong> recupera acceso al
        módulo con los roles que tenía al momento de la inactivación.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de reactivación"
        id="usr-reactivar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button
          type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="usr-reactivar-submit"
        >{hook.submitting ? 'Reactivando…' : 'Reactivar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div
      role="dialog" aria-modal="true" data-testid={testid}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 520, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function ModalFoot({ onClose, children }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
      <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
      {children}
    </div>
  );
}

export default AdminUsuarios;
