/**
 * TablaTRD — GD-UI-0045/0046. Consulta + edición de TRD jerárquica.
 *
 * Vista navegable: series → subseries → tipos documentales. Para roles
 * con TRD-001/003 (admin documental) se habilitan formularios de
 * creación inline. Para nueva versión + aprobación, modal aparte
 * (TRD-002, requiere acta de comité — el cuerpo se captura como
 * justificación).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useTRD, useTRDVersionActual, useVersionesTRD,
  useCrearSerie, useCrearSubserie, useCrearTipoDocumental,
  useNuevaVersionTRD, useAprobarVersionTRD, useEliminarSerie,
} from './useGdTRD.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function TablaTRD({ session, roles = [], ...shellProps }) {
  const { items: series, loading, error, refresh } = useTRD(session);
  const { data: versionActual } = useTRDVersionActual(session);
  const [expandidas, setExpandidas] = useState({});
  const [modal, setModal] = useState(null);
  const [editar, setEditar] = useState(null);
  const puedeEditar = gdCanAny(roles, 'TRD-001', 'RW');
  const puedeVersionar = gdCanAny(roles, 'TRD-002', 'RW');

  function toggle(id) {
    setExpandidas((p) => ({ ...p, [id]: !p[id] }));
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'TRD' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Tabla de Retención Documental</h1>
          <p className="subtitle">
            {versionActual
              ? <>Versión vigente <strong>v{versionActual.numero}</strong> aprobada el {fmt(versionActual.aprobada_en)}.</>
              : 'Sin versión vigente aprobada.'}
          </p>
        </div>
        <div className="actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            data-testid="trd-refresh"
          >Actualizar</button>
          {puedeEditar && (
            <button
              type="button"
              className="btn btn-accent"
              onClick={() => setModal('nueva-serie')}
              data-testid="trd-nueva-serie"
            >+ Nueva serie</button>
          )}
          {puedeVersionar && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModal('nueva-version')}
              data-testid="trd-nueva-version"
            >Nueva versión TRD</button>
          )}
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && series.length === 0 && (
        <div className="empty" data-testid="trd-empty">
          <p className="muted">No hay series registradas todavía.</p>
        </div>
      )}

      {series.length > 0 && (
        <div className="card" style={{ padding: 0 }} data-testid="trd-tree">
          {series.map((s) => (
            <SerieRow
              key={s.id}
              serie={s}
              expanded={!!expandidas[s.id]}
              onToggle={() => toggle(s.id)}
              session={session}
              roles={roles}
              onAddSubserie={() => setEditar({ tipo: 'subserie', serieId: s.id })}
              onAddTipo={(subserieId) => setEditar({ tipo: 'tipo', subserieId })}
              onEliminarSerie={() => setEditar({ tipo: 'eliminar-serie', serie: s })}
            />
          ))}
        </div>
      )}

      {modal === 'nueva-serie' && (
        <SerieFormModal
          session={session}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {modal === 'nueva-version' && (
        <NuevaVersionTRDModal
          session={session}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); refresh(); }}
        />
      )}
      {editar?.tipo === 'subserie' && (
        <SubserieFormModal
          session={session}
          serieId={editar.serieId}
          onClose={() => setEditar(null)}
          onSuccess={() => { setEditar(null); refresh(); }}
        />
      )}
      {editar?.tipo === 'tipo' && (
        <TipoFormModal
          session={session}
          subserieId={editar.subserieId}
          onClose={() => setEditar(null)}
          onSuccess={() => { setEditar(null); refresh(); }}
        />
      )}
      {editar?.tipo === 'eliminar-serie' && (
        <EliminarSerieModal
          session={session}
          serie={editar.serie}
          onClose={() => setEditar(null)}
          onSuccess={() => { setEditar(null); refresh(); }}
        />
      )}
    </GdShell>
  );
}

function SerieRow({
  serie, expanded, onToggle, session: _s, roles,
  onAddSubserie, onAddTipo, onEliminarSerie,
}) {
  const puedeEditar = gdCanAny(roles, 'TRD-001', 'RW');
  return (
    <div data-testid="trd-serie" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center',
          padding: 'var(--s-3) var(--s-4)',
          background: expanded ? 'var(--surface-alt)' : 'transparent',
        }}
      >
        <button
          type="button" className="btn-icon"
          onClick={onToggle}
          aria-label={expanded ? 'Colapsar' : 'Expandir'}
          data-testid="trd-serie-toggle"
        >{expanded ? '▾' : '▸'}</button>
        <div style={{ flex: 1 }}>
          <strong style={{ fontSize: 14 }}>{serie.codigo} — {serie.nombre}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            {(serie.subseries || []).length} subserie(s)
          </div>
        </div>
        {puedeEditar && (
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onAddSubserie}
              data-testid="trd-add-subserie"
            >+ Subserie</button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={onEliminarSerie}
              data-testid="trd-eliminar-serie"
            >Inactivar</button>
          </div>
        )}
      </div>
      {expanded && (
        <div style={{ padding: 'var(--s-3) var(--s-5)', background: 'var(--surface-subtle)' }}>
          {(serie.subseries || []).length === 0 && (
            <p className="muted" style={{ fontSize: 12 }}>Sin subseries.</p>
          )}
          {(serie.subseries || []).map((ss) => (
            <div key={ss.id} data-testid="trd-subserie" style={{ marginBottom: 'var(--s-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>
                  {ss.codigo} — {ss.nombre}
                </span>
                {puedeEditar && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => onAddTipo(ss.id)}
                    data-testid="trd-add-tipo"
                  >+ Tipo</button>
                )}
              </div>
              {(ss.tipos || []).length > 0 && (
                <ul style={{ margin: '4px 0 4px 24px', fontSize: 12 }}>
                  {ss.tipos.map((t) => (
                    <li key={t.id} data-testid="trd-tipo">
                      {t.codigo ? `${t.codigo} · ` : ''}{t.nombre}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
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
      <div onClick={(e) => e.stopPropagation()} className="card"
        style={{ width: 500, padding: 'var(--s-5)' }}>
        <h2 style={{ margin: 0, fontSize: 16, marginBottom: 'var(--s-3)' }}>{title}</h2>
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

function SerieFormModal({ session, onClose, onSuccess }) {
  const [form, setForm] = useState({ codigo: '', nombre: '', descripcion: '' });
  const hook = useCrearSerie(session);

  async function handle() {
    try {
      await hook.submit(form);
      onSuccess?.();
    } catch { /* hook */ }
  }
  const valid = form.codigo.trim().length >= 1 && form.nombre.trim().length >= 2;

  return (
    <ModalShell title="Nueva serie documental" onClose={onClose} testid="trd-serie-modal">
      <div className="field">
        <label>Código <span className="req">*</span></label>
        <input className="input" value={form.codigo}
          onChange={(e) => setForm({ ...form, codigo: e.target.value })}
          data-testid="trd-serie-codigo" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Nombre <span className="req">*</span></label>
        <input className="input" value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          data-testid="trd-serie-nombre" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea className="textarea" rows={2} value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          data-testid="trd-serie-desc" />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="trd-serie-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function SubserieFormModal({ session, serieId, onClose, onSuccess }) {
  const [form, setForm] = useState({ codigo: '', nombre: '' });
  const hook = useCrearSubserie(session);
  async function handle() {
    try { await hook.submit(serieId, form); onSuccess?.(); } catch { /* */ }
  }
  const valid = form.codigo.trim().length >= 1 && form.nombre.trim().length >= 2;
  return (
    <ModalShell title="Nueva subserie" onClose={onClose} testid="trd-subserie-modal">
      <div className="field">
        <label>Código <span className="req">*</span></label>
        <input className="input" value={form.codigo}
          onChange={(e) => setForm({ ...form, codigo: e.target.value })}
          data-testid="trd-subserie-codigo" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Nombre <span className="req">*</span></label>
        <input className="input" value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          data-testid="trd-subserie-nombre" />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="trd-subserie-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function TipoFormModal({ session, subserieId, onClose, onSuccess }) {
  const [form, setForm] = useState({ codigo: '', nombre: '' });
  const hook = useCrearTipoDocumental(session);
  async function handle() {
    try { await hook.submit(subserieId, form); onSuccess?.(); } catch { /* */ }
  }
  const valid = form.nombre.trim().length >= 2;
  return (
    <ModalShell title="Nuevo tipo documental" onClose={onClose} testid="trd-tipo-modal">
      <div className="field">
        <label>Código</label>
        <input className="input" value={form.codigo}
          onChange={(e) => setForm({ ...form, codigo: e.target.value })}
          data-testid="trd-tipo-codigo" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Nombre <span className="req">*</span></label>
        <input className="input" value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          data-testid="trd-tipo-nombre" />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="trd-tipo-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function EliminarSerieModal({ session, serie, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useEliminarSerie(session);
  async function handle() {
    try { await hook.submit(serie.id, motivo); onSuccess?.(); } catch { /* */ }
  }
  return (
    <ModalShell title="Inactivar serie" onClose={onClose} testid="trd-eliminar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        La serie <strong>{serie.codigo}</strong> dejará de estar disponible
        para clasificación. Los documentos ya clasificados se conservan.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="trd-eliminar-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="trd-eliminar-submit"
        >{hook.submitting ? 'Inactivando…' : 'Inactivar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function NuevaVersionTRDModal({ session, onClose, onSuccess }) {
  const [obs, setObs] = useState('');
  const [acta, setActa] = useState('');
  const [valid, setValid] = useState(false);
  const crearV = useNuevaVersionTRD(session);
  const aprobar = useAprobarVersionTRD(session);
  const versiones = useVersionesTRD(session);

  async function handle() {
    try {
      const v = await crearV.submit({ observaciones: obs });
      if (v?.id) {
        await aprobar.submit(v.id, { acta_comite: acta });
      }
      onSuccess?.();
    } catch { /* hook */ }
  }

  const isValid = valid && acta.trim().length >= 5;
  const submitting = crearV.submitting || aprobar.submitting;
  const error = crearV.error || aprobar.error;

  return (
    <ModalShell
      title="Nueva versión de TRD" onClose={onClose}
      testid="trd-nueva-version-modal"
    >
      <p className="muted" style={{ fontSize: 13 }}>
        La nueva versión consolida los cambios pendientes en TRD. La
        aprobación formal requiere el acta del Comité de Archivo.
      </p>
      {versiones.items.length > 0 && (
        <p className="muted" style={{ fontSize: 12 }}>
          {versiones.items.length} versión(es) previa(s) registrada(s).
        </p>
      )}
      <JustificacionRequiredField
        value={obs}
        onChange={(v, ok) => { setObs(v); setValid(ok); }}
        label="Resumen de cambios"
        id="trd-version-obs"
      />
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Acta del Comité de Archivo <span className="req">*</span></label>
        <input className="input" value={acta}
          onChange={(e) => setActa(e.target.value)}
          placeholder="Acta 0001 / 2026"
          data-testid="trd-version-acta" />
      </div>
      {error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!isValid || submitting} onClick={handle}
          data-testid="trd-version-submit"
        >{submitting ? 'Procesando…' : 'Crear y aprobar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-CO'); }
  catch { return iso; }
}

export default TablaTRD;
