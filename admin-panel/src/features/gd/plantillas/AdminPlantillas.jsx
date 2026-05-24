/**
 * AdminPlantillas — GD-UI-0039. CRUD de plantillas institucionales.
 *
 * Layout: lista + panel derecho con detalle / creación / edición.
 * Versionado: cada cambio relevante crea nueva versión.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  usePlantillasList,
  usePlantilla,
  useCrearPlantilla,
  useActualizarPlantilla,
  useNuevaVersionPlantilla,
  useInactivarPlantilla,
} from './useGdPlantillas.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

const TIPOS_PLANTILLA = [
  'oficio', 'memorando', 'constancia', 'certificado',
  'resolucion', 'acta', 'circular', 'comunicado',
];

export function AdminPlantillas({ session, roles = [], onNavigate, ...shellProps }) {
  const [selectedId, setSelectedId] = useState(null);
  const [mode, setMode] = useState('view'); // view | edit | new | nuevaver
  const { items, loading, error, refresh } = usePlantillasList(session, {});
  const puedeEditar = gdCanAny(roles, 'PLA-001', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Plantillas' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Plantillas documentales</h1>
          <p className="subtitle">
            {items.length} plantilla(s) institucional(es). El versionado
            preserva cada cambio mayor.
          </p>
        </div>
        <div className="actions">
          {puedeEditar && (
            <button
              type="button"
              className="btn btn-accent"
              onClick={() => { setSelectedId(null); setMode('new'); }}
              data-testid="plt-new"
            >+ Nueva plantilla</button>
          )}
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '320px 1fr',
          gap: 'var(--s-4)',
        }}
        data-testid="plt-layout"
      >
        <aside className="card" style={{ padding: 0, overflow: 'hidden' }}>
          {loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
          {error && (
            <div className="alert danger" role="alert" style={{ margin: 'var(--s-3)' }}>
              <div className="body">{error.message || 'Error.'}</div>
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <div className="empty" data-testid="plt-empty">
              <p>No hay plantillas registradas.</p>
            </div>
          )}
          {items.map((p) => (
            <button
              key={p.id}
              type="button"
              data-testid="plt-row"
              onClick={() => { setSelectedId(p.id); setMode('view'); }}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: 'var(--s-3) var(--s-4)',
                border: 0,
                borderBottom: '1px solid var(--border-subtle)',
                background: selectedId === p.id ? 'var(--sky-50)' : 'transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13 }}>{p.nombre}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                {p.tipo} · v{p.version_actual}{!p.activa && ' · inactiva'}
              </div>
            </button>
          ))}
        </aside>

        <section className="card" style={{ padding: 'var(--s-5)' }}>
          {mode === 'view' && selectedId && (
            <DetallePlantilla
              session={session}
              plantillaId={selectedId}
              roles={roles}
              onEdit={() => setMode('edit')}
              onNuevaVersion={() => setMode('nuevaver')}
              onInactivar={() => setMode('inactivar')}
              onGenerar={() => onNavigate?.(`/gd/plantillas/${selectedId}/generar`)}
            />
          )}
          {mode === 'view' && !selectedId && (
            <p className="muted">Seleccione una plantilla o cree una nueva.</p>
          )}
          {mode === 'new' && (
            <FormPlantilla
              session={session}
              onCancel={() => setMode('view')}
              onSuccess={() => { setMode('view'); refresh(); }}
            />
          )}
          {mode === 'edit' && selectedId && (
            <FormPlantilla
              session={session}
              plantillaId={selectedId}
              onCancel={() => setMode('view')}
              onSuccess={() => { setMode('view'); refresh(); }}
            />
          )}
          {mode === 'nuevaver' && selectedId && (
            <FormNuevaVersion
              session={session}
              plantillaId={selectedId}
              onCancel={() => setMode('view')}
              onSuccess={() => { setMode('view'); refresh(); }}
            />
          )}
          {mode === 'inactivar' && selectedId && (
            <FormInactivar
              session={session}
              plantillaId={selectedId}
              onCancel={() => setMode('view')}
              onSuccess={() => { setMode('view'); refresh(); }}
            />
          )}
        </section>
      </div>
    </GdShell>
  );
}

function DetallePlantilla({ session, plantillaId, roles, onEdit, onNuevaVersion, onInactivar, onGenerar }) {
  const { data: p, loading, error } = usePlantilla(session, plantillaId);
  const puedeEditar = gdCanAny(roles, 'PLA-001', 'RW');
  const puedeGenerar = gdCanAny(roles, 'PLA-USE', 'R');

  if (loading) return <p className="muted">Cargando…</p>;
  if (error) return (
    <div className="alert danger" role="alert">
      <div className="body">{error.message || 'Error.'}</div>
    </div>
  );
  if (!p) return null;

  return (
    <div data-testid="plt-detalle">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>{p.nombre}</h2>
      <Row label="Tipo" value={p.tipo} />
      <Row label="Versión actual" value={`v${p.version_actual}`} />
      <Row label="Estado" value={p.activa ? 'Activa' : 'Inactiva'} />
      <Row label="Descripción" value={p.descripcion} />
      {(p.variables || []).length > 0 && (
        <div style={{ marginTop: 'var(--s-3)' }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Variables</div>
          <ul style={{ margin: 0, paddingLeft: 16 }} data-testid="plt-variables">
            {p.variables.map((v) => (
              <li key={v.nombre} style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>
                {`{{${v.nombre}}}`} <span className="muted">— {v.descripcion || v.tipo}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)', flexWrap: 'wrap' }}>
        {puedeGenerar && p.activa && (
          <button type="button" className="btn btn-accent"
            onClick={onGenerar}
            data-testid="plt-generar"
          >Generar documento</button>
        )}
        {puedeEditar && (
          <>
            <button type="button" className="btn btn-secondary"
              onClick={onEdit}
              data-testid="plt-edit"
            >Editar metadata</button>
            <button type="button" className="btn btn-secondary"
              onClick={onNuevaVersion}
              data-testid="plt-nueva-version"
            >Nueva versión</button>
            {p.activa && (
              <button type="button" className="btn btn-danger"
                onClick={onInactivar}
                data-testid="plt-inactivar"
              >Inactivar</button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function FormPlantilla({ session, plantillaId, onCancel, onSuccess }) {
  const isEdit = Boolean(plantillaId);
  const { data: existente } = usePlantilla(session, plantillaId, { enabled: isEdit });
  const [form, setForm] = useState({
    nombre: '', tipo: 'oficio', descripcion: '', cuerpo: '', variables: [],
  });
  const [initialized, setInitialized] = useState(false);

  React.useEffect(() => {
    if (existente && !initialized) {
      setForm({
        nombre: existente.nombre || '',
        tipo: existente.tipo || 'oficio',
        descripcion: existente.descripcion || '',
        cuerpo: existente.cuerpo || '',
        variables: existente.variables || [],
      });
      setInitialized(true);
    }
  }, [existente, initialized]);

  const crear = useCrearPlantilla(session);
  const editar = useActualizarPlantilla(session);
  const hook = isEdit ? editar : crear;

  function update(k, v) { setForm((p) => ({ ...p, [k]: v })); }

  async function handle() {
    try {
      if (isEdit) {
        await editar.submit(plantillaId, form);
      } else {
        await crear.submit(form);
      }
      onSuccess?.();
    } catch { /* hook */ }
  }

  const isValid = form.nombre.trim().length >= 2 && form.tipo;

  return (
    <div data-testid="plt-form">
      <h2 style={{ fontSize: 16, marginTop: 0 }}>
        {isEdit ? 'Editar plantilla' : 'Nueva plantilla'}
      </h2>
      <div className="field">
        <label>Nombre <span className="req">*</span></label>
        <input
          className="input"
          value={form.nombre}
          onChange={(e) => update('nombre', e.target.value)}
          data-testid="plt-form-nombre"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Tipo</label>
        <select
          className="select"
          value={form.tipo}
          onChange={(e) => update('tipo', e.target.value)}
          data-testid="plt-form-tipo"
        >
          {TIPOS_PLANTILLA.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea
          className="textarea"
          rows={2}
          value={form.descripcion}
          onChange={(e) => update('descripcion', e.target.value)}
          data-testid="plt-form-desc"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Cuerpo (HTML / texto con variables {`{{nombre}}`})</label>
        <textarea
          className="textarea"
          rows={8}
          value={form.cuerpo}
          onChange={(e) => update('cuerpo', e.target.value)}
          data-testid="plt-form-cuerpo"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancelar</button>
        <button
          type="button"
          className="btn btn-accent"
          disabled={!isValid || hook.submitting}
          onClick={handle}
          data-testid="plt-form-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </div>
    </div>
  );
}

function FormNuevaVersion({ session, plantillaId, onCancel, onSuccess }) {
  const [cuerpo, setCuerpo] = useState('');
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useNuevaVersionPlantilla(session);

  async function handle() {
    try {
      await hook.submit(plantillaId, { cuerpo, motivo });
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div data-testid="plt-nuevaver-form">
      <h2 style={{ fontSize: 16, marginTop: 0 }}>Nueva versión</h2>
      <div className="field">
        <label>Cuerpo de la nueva versión <span className="req">*</span></label>
        <textarea
          className="textarea"
          rows={10}
          value={cuerpo}
          onChange={(e) => setCuerpo(e.target.value)}
          data-testid="plt-nuevaver-cuerpo"
        />
      </div>
      <div style={{ marginTop: 'var(--s-3)' }}>
        <JustificacionRequiredField
          value={motivo}
          onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
          label="Motivo de la nueva versión"
          id="plt-motivo-version"
        />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancelar</button>
        <button
          type="button"
          className="btn btn-accent"
          disabled={!cuerpo.trim() || !valid || hook.submitting}
          onClick={handle}
          data-testid="plt-nuevaver-submit"
        >{hook.submitting ? 'Guardando…' : 'Crear versión'}</button>
      </div>
    </div>
  );
}

function FormInactivar({ session, plantillaId, onCancel, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarPlantilla(session);

  async function handle() {
    try {
      await hook.submit(plantillaId, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <div data-testid="plt-inactivar-form">
      <h2 style={{ fontSize: 16, marginTop: 0 }}>Inactivar plantilla</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        La plantilla no podrá usarse para generar nuevos documentos.
        Los documentos generados con ella siguen siendo válidos.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="plt-inactivar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancelar</button>
        <button
          type="button"
          className="btn btn-danger-solid"
          disabled={!valid || hook.submitting}
          onClick={handle}
          data-testid="plt-inactivar-submit"
        >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div
      style={{
        display: 'grid', gridTemplateColumns: '180px 1fr',
        padding: '6px 0', borderBottom: '1px dashed var(--border-subtle)',
        fontSize: 14,
      }}
    >
      <span className="muted" style={{ fontSize: 12 }}>{label}</span>
      <span>{value || '—'}</span>
    </div>
  );
}

export default AdminPlantillas;
