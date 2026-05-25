/**
 * AdminEstructura — GD-UI-0055/0056. Estructura orgánica (árbol).
 *
 * Vista jerárquica de dependencias con jefe asignado. Crear /
 * editar / reubicar / inactivar con motivo (USR-009 + EST-001).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useEstructuraOrganica,
  useCrearVersionEstructura,
  useCrearDependencia, useActualizarDependencia,
  useReubicarDependencia, useInactivarDependencia,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function AdminEstructura({ session, roles = [], ...shellProps }) {
  const { data, loading, error, refresh } = useEstructuraOrganica(session);
  const [expandidas, setExpandidas] = useState({});
  const [modal, setModal] = useState(null);
  const puedeEditar = gdCanAny(roles, 'EST-001', 'RW');

  const dependencias = data?.dependencias || data?.items || (Array.isArray(data) ? data : []);
  // Versión vigente — el backend devuelve `version_estructura_id` en el
  // shape de `/admin/estructura/vigente`. Si no existe, el tenant está
  // arrancando "desde cero": NO se puede crear ninguna dependencia hasta
  // que se cree la primera versión (DependenciaCreate.version_estructura_id
  // es required).
  const versionVigenteId = data?.version_estructura_id || data?.version_id || data?.id || null;
  const sinVersion = !loading && !error && !versionVigenteId;

  function toggle(id) {
    setExpandidas((p) => ({ ...p, [id]: !p[id] }));
  }

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Estructura orgánica' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Estructura orgánica</h1>
          <p className="subtitle">
            Árbol de dependencias y secciones administrativas de la entidad.
          </p>
        </div>
        <div className="actions">
          <button
            type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="est-refresh"
          >Actualizar</button>
          {puedeEditar && sinVersion && (
            <button
              type="button" className="btn btn-accent"
              onClick={() => setModal({ tipo: 'nueva-version' })}
              data-testid="est-nueva-version"
            >+ Crear primera versión</button>
          )}
          {puedeEditar && !sinVersion && (
            <>
              <button
                type="button" className="btn btn-secondary"
                onClick={() => setModal({ tipo: 'nueva-version' })}
                data-testid="est-nueva-version"
                title="Versionar la estructura (apertura de nueva vigencia)"
              >Nueva versión</button>
              <button
                type="button" className="btn btn-accent"
                onClick={() => setModal({ tipo: 'nueva', padre_id: null })}
                data-testid="est-nueva"
              >+ Nueva dependencia raíz</button>
            </>
          )}
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {sinVersion && (
        <div className="empty" data-testid="est-sin-version" style={{ textAlign: 'center', padding: 'var(--s-6)' }}>
          <h2 style={{ marginTop: 0 }}>Aún no hay estructura orgánica</h2>
          <p className="muted">
            La <strong>primera versión</strong> de la estructura orgánica
            debe crearse antes de cargar dependencias. Tip: usá el número
            de versión del acto administrativo que la aprueba
            (ej. <em>"Decreto 001 de {new Date().getFullYear()}"</em>).
          </p>
          {puedeEditar && (
            <button
              type="button" className="btn btn-accent"
              onClick={() => setModal({ tipo: 'nueva-version' })}
              data-testid="est-sin-version-cta"
              style={{ marginTop: 'var(--s-3)' }}
            >+ Crear primera versión</button>
          )}
        </div>
      )}
      {!loading && !error && !sinVersion && dependencias.length === 0 && (
        <div className="empty" data-testid="est-empty">
          <p>No hay dependencias registradas.</p>
        </div>
      )}
      {dependencias.length > 0 && (
        <div className="card" style={{ padding: 0 }} data-testid="est-tree">
          {dependencias.map((d) => (
            <DependenciaNodo
              key={d.id}
              dep={d}
              nivel={0}
              expandidas={expandidas}
              onToggle={toggle}
              puedeEditar={puedeEditar}
              onEditar={(dep) => setModal({ tipo: 'editar', dep })}
              onAgregarHija={(padre) => setModal({ tipo: 'nueva', padre_id: padre.id })}
              onReubicar={(dep) => setModal({ tipo: 'reubicar', dep })}
              onInactivar={(dep) => setModal({ tipo: 'inactivar', dep })}
            />
          ))}
        </div>
      )}

      {modal?.tipo === 'nueva-version' && (
        <NuevaVersionModal
          session={session}
          tieneVigente={!sinVersion}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal?.tipo === 'nueva' && (
        <FormDepModal
          session={session}
          padreId={modal.padre_id}
          // version_estructura_id requerido por el backend
          // (DependenciaCreate). Lo leemos del response de
          // /admin/estructura/vigente.
          versionEstructuraId={versionVigenteId}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal?.tipo === 'editar' && (
        <FormDepModal
          session={session}
          dep={modal.dep}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal?.tipo === 'reubicar' && (
        <ReubicarModal
          session={session}
          dep={modal.dep}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal?.tipo === 'inactivar' && (
        <InactivarDepModal
          session={session}
          dep={modal.dep}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function DependenciaNodo({
  dep, nivel, expandidas, onToggle, puedeEditar,
  onEditar, onAgregarHija, onReubicar, onInactivar,
}) {
  const hijas = dep.hijas || dep.children || [];
  const expanded = !!expandidas[dep.id];
  return (
    <div data-testid="est-nodo" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: 'var(--s-3) var(--s-4)',
        paddingLeft: `calc(var(--s-4) + ${nivel * 24}px)`,
      }}>
        {hijas.length > 0 ? (
          <button
            type="button" className="btn-icon"
            onClick={() => onToggle(dep.id)}
            aria-label={expanded ? 'Colapsar' : 'Expandir'}
            data-testid="est-nodo-toggle"
          >{expanded ? '▾' : '▸'}</button>
        ) : (
          <span style={{ width: 24 }}></span>
        )}
        <div style={{ flex: 1 }}>
          <strong style={{ fontSize: 14 }}>{dep.codigo} — {dep.nombre}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            Jefe: {dep.jefe_nombre || '—'}
            {!dep.activa && ' · inactiva'}
          </div>
        </div>
        {puedeEditar && (
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="button" className="btn btn-secondary btn-sm"
              onClick={() => onEditar(dep)}
              data-testid="est-nodo-editar"
            >Editar</button>
            <button type="button" className="btn btn-secondary btn-sm"
              onClick={() => onAgregarHija(dep)}
              data-testid="est-nodo-agregar"
            >+ Hija</button>
            <button type="button" className="btn btn-secondary btn-sm"
              onClick={() => onReubicar(dep)}
              data-testid="est-nodo-reubicar"
            >Reubicar</button>
            {dep.activa !== false && (
              <button type="button" className="btn btn-danger btn-sm"
                onClick={() => onInactivar(dep)}
                data-testid="est-nodo-inactivar"
              >Inactivar</button>
            )}
          </div>
        )}
      </div>
      {expanded && hijas.map((h) => (
        <DependenciaNodo
          key={h.id} dep={h} nivel={nivel + 1}
          expandidas={expandidas} onToggle={onToggle}
          puedeEditar={puedeEditar}
          onEditar={onEditar} onAgregarHija={onAgregarHija}
          onReubicar={onReubicar} onInactivar={onInactivar}
        />
      ))}
    </div>
  );
}

/**
 * Modal "Crear primera/nueva versión de estructura orgánica".
 *
 * Llama POST /v1/gd/admin/estructura/versiones (VersionEstructuraCreate).
 * Es el primer paso del "flujo desde cero" en un tenant recién activado:
 * sin una versión vigente NO se puede crear ninguna dependencia.
 */
function NuevaVersionModal({ session, tieneVigente, onClose, onSuccess }) {
  const hoy = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    numero_version: '',
    acto_administrativo: '',
    descripcion: '',
    fecha_inicio_vigencia: hoy,
  });
  const hook = useCrearVersionEstructura(session);

  async function handle() {
    try {
      await hook.submit({
        numero_version: form.numero_version.trim(),
        acto_administrativo: form.acto_administrativo.trim() || null,
        descripcion: form.descripcion.trim() || null,
        fecha_inicio_vigencia: form.fecha_inicio_vigencia,
      });
      onSuccess?.();
    } catch { /* hook */ }
  }

  const valid = form.numero_version.trim().length >= 1
    && form.fecha_inicio_vigencia;

  return (
    <ModalShell
      title={tieneVigente ? 'Nueva versión de estructura' : 'Crear primera versión de estructura'}
      onClose={onClose}
      testid="est-version-modal"
    >
      <p className="muted" style={{ fontSize: 13 }}>
        {tieneVigente
          ? 'Versionar abre una nueva vigencia. Las dependencias actuales se conservan; podés modificarlas dentro de la nueva versión.'
          : 'La estructura orgánica es versionada: cada cambio mayor abre una nueva vigencia trazable al acto administrativo que la aprueba.'}
      </p>
      <div className="field">
        <label>Número de versión <span className="req">*</span></label>
        <input className="input" value={form.numero_version}
          onChange={(e) => setForm({ ...form, numero_version: e.target.value })}
          placeholder={`Ej. v1, ${new Date().getFullYear()}, Decreto-001`}
          data-testid="est-version-numero" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Acto administrativo</label>
        <input className="input" value={form.acto_administrativo}
          onChange={(e) => setForm({ ...form, acto_administrativo: e.target.value })}
          placeholder={`Ej. Decreto 001 de ${new Date().getFullYear()}`}
          data-testid="est-version-acto" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea className="input" rows={3} value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          placeholder="Breve descripción del cambio estructural."
          data-testid="est-version-descripcion" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Fecha de inicio de vigencia <span className="req">*</span></label>
        <input className="input" type="date" value={form.fecha_inicio_vigencia}
          onChange={(e) => setForm({ ...form, fecha_inicio_vigencia: e.target.value })}
          data-testid="est-version-fecha" />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body" style={{ whiteSpace: 'pre-line' }}>
            {hook.error.message || 'Error.'}
          </div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="est-version-submit"
        >{hook.submitting ? 'Creando…' : 'Crear versión'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function FormDepModal({
  session, dep, padreId,
  versionEstructuraId,   // UUID de la versión vigente; required para crear
  onClose, onSuccess,
}) {
  const isEdit = Boolean(dep);
  // Schema canónico backend: `DependenciaCreate`
  // (app/gd/schemas/dependencias.py:61). Campos REQUERIDOS:
  //   - codigo_organico       (1-40 chars, identificador en organigrama)
  //   - nombre                (2-300 chars)
  //   - fecha_inicio_vigencia (date — cuándo entra en vigencia esta unidad)
  //   - version_estructura_id (UUID — debe existir una versión TRD activa
  //                            del organigrama; pasada via prop o contexto)
  // Opcional: dependencia_padre_id (UUID — null = raíz).
  //
  // IMPORTANTE: `version_estructura_id` lo pasa el componente padre
  // (AdminEstructura) leyendo el `data?.version_id` que devuelve
  // `getEstructuraOrganica` (= `/admin/estructura/vigente`). Si NO hay
  // versión vigente, el botón "Nueva dependencia" debería estar deshabilitado.
  const hoy = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    codigo_organico: dep?.codigo_organico || '',
    nombre: dep?.nombre || '',
    fecha_inicio_vigencia: dep?.fecha_inicio_vigencia || hoy,
    dependencia_padre_id: padreId ?? dep?.dependencia_padre_id ?? '',
  });
  const crear = useCrearDependencia(session);
  const editar = useActualizarDependencia(session);
  const hook = isEdit ? editar : crear;

  async function handle() {
    try {
      if (isEdit) {
        // Backend PATCH solo acepta nombre + dependencia_padre_id.
        await editar.submit(dep.id, {
          nombre: form.nombre.trim(),
          dependencia_padre_id: form.dependencia_padre_id || null,
        });
      } else {
        if (!versionEstructuraId) {
          // Defensa adicional: el padre debería haberlo prevenido.
          throw new Error(
            'No hay versión de estructura orgánica vigente. '
            + 'Primero creá una versión desde "Estructura → Nueva versión".',
          );
        }
        await crear.submit({
          codigo_organico: form.codigo_organico.trim(),
          nombre: form.nombre.trim(),
          fecha_inicio_vigencia: form.fecha_inicio_vigencia,
          version_estructura_id: versionEstructuraId,
          dependencia_padre_id: form.dependencia_padre_id || null,
        });
      }
      onSuccess?.();
    } catch { /* hook */ }
  }

  const valid =
    form.codigo_organico.trim().length >= 1
    && form.nombre.trim().length >= 2
    && (isEdit || (form.fecha_inicio_vigencia && versionEstructuraId));

  return (
    <ModalShell title={isEdit ? 'Editar dependencia' : 'Nueva dependencia'} onClose={onClose} testid="est-form-modal">
      {!isEdit && !versionEstructuraId && (
        <div className="alert warning" role="alert" style={{ marginBottom: 12 }}>
          <div className="body">
            No hay versión de estructura orgánica vigente. Primero creá una
            versión desde la pantalla "Estructura → Nueva versión" antes
            de agregar dependencias.
          </div>
        </div>
      )}
      <div className="field">
        <label>Código orgánico <span className="req">*</span></label>
        <input className="input" value={form.codigo_organico}
          onChange={(e) => setForm({ ...form, codigo_organico: e.target.value })}
          placeholder="Ej. 1000, 1200, 1210 (alineado al organigrama)"
          data-testid="est-form-codigo" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Nombre <span className="req">*</span></label>
        <input className="input" value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          data-testid="est-form-nombre" />
      </div>
      {!isEdit && (
        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Fecha de inicio de vigencia <span className="req">*</span></label>
          <input className="input" type="date" value={form.fecha_inicio_vigencia}
            onChange={(e) => setForm({ ...form, fecha_inicio_vigencia: e.target.value })}
            data-testid="est-form-fecha" />
        </div>
      )}
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body" style={{ whiteSpace: 'pre-line' }}>
            {hook.error.message || 'Error.'}
          </div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="est-form-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function ReubicarModal({ session, dep, onClose, onSuccess }) {
  const [nuevoPadre, setNuevoPadre] = useState('');
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useReubicarDependencia(session);

  async function handle() {
    try {
      await hook.submit(dep.id, nuevoPadre || null, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title={`Reubicar ${dep.nombre}`} onClose={onClose} testid="est-reubicar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        Cambiar el padre jerárquico de esta dependencia afecta la cadena
        de autoridad. Use solo cuando se haya emitido el acto administrativo
        correspondiente.
      </p>
      <div className="field">
        <label>UUID del nuevo padre (vacío = raíz)</label>
        <input className="input" value={nuevoPadre}
          onChange={(e) => setNuevoPadre(e.target.value)}
          data-testid="est-reubicar-padre" />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Motivo de la reubicación"
          id="est-reubicar-motivo"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="est-reubicar-submit"
        >{hook.submitting ? 'Reubicando…' : 'Reubicar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function InactivarDepModal({ session, dep, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarDependencia(session);

  async function handle() {
    try {
      await hook.submit(dep.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title={`Inactivar ${dep.nombre}`} onClose={onClose} testid="est-inactivar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        La dependencia <strong>{dep.codigo}</strong> dejará de estar
        disponible para asignaciones nuevas. Los expedientes y usuarios
        asociados deben migrarse antes.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="est-inactivar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="est-inactivar-submit"
        >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
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

export default AdminEstructura;
