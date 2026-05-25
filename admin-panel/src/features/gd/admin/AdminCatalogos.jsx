/**
 * AdminCatalogos — GD-UI-0057. Catálogos institucionales.
 *
 * Lista de catálogos disponibles (canales, tipos de tercero, etc) y
 * gestión CRUD de sus ítems (CAT-001).
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useCatalogosLista, useItemsCatalogo,
  useCrearItemCatalogo, useActualizarItemCatalogo, useInactivarItemCatalogo,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function AdminCatalogos({ session, roles = [], ...shellProps }) {
  const cat = useCatalogosLista(session);
  const [codigoSel, setCodigoSel] = useState(null);
  const [modal, setModal] = useState(null);
  const items = useItemsCatalogo(session, codigoSel, { enabled: !!codigoSel });
  const puedeEditar = gdCanAny(roles, 'CAT-001', 'RW');

  return (
    <GdShell
      roles={roles}
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Catálogos institucionales' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Catálogos institucionales</h1>
          <p className="subtitle">
            {cat.items.length} catálogo(s) configurable(s) en el módulo.
          </p>
        </div>
      </div>

      <div
        data-testid="cat-layout"
        style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 'var(--s-4)' }}
      >
        <aside className="card" style={{ padding: 0 }}>
          {cat.loading && <p className="muted" style={{ padding: 'var(--s-4)' }}>Cargando…</p>}
          {cat.error && (
            <div className="alert danger" role="alert" style={{ margin: 'var(--s-3)' }}>
              <div className="body">{cat.error.message || 'Error.'}</div>
            </div>
          )}
          {!cat.loading && !cat.error && cat.items.length === 0 && (
            <div className="empty" data-testid="cat-empty"><p>Sin catálogos.</p></div>
          )}
          {cat.items.map((c) => (
            <button
              key={c.codigo}
              type="button"
              data-testid="cat-row"
              onClick={() => setCodigoSel(c.codigo)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: 'var(--s-3)',
                border: 0,
                borderBottom: '1px solid var(--border-subtle)',
                background: codigoSel === c.codigo ? 'var(--sky-50)' : 'transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13 }}>{c.nombre || c.codigo}</div>
              <div className="muted" style={{ fontSize: 11 }}>
                {c.total ?? c.items?.length ?? 0} ítem(s)
              </div>
            </button>
          ))}
        </aside>

        <section className="card" style={{ padding: 'var(--s-5)' }}>
          {!codigoSel && (
            <p className="muted">Seleccione un catálogo para ver sus ítems.</p>
          )}
          {codigoSel && (
            <ItemsCatalogo
              codigo={codigoSel}
              items={items.items}
              loading={items.loading}
              error={items.error}
              puedeEditar={puedeEditar}
              onAdd={() => setModal({ tipo: 'nuevo' })}
              onEditar={(it) => setModal({ tipo: 'editar', item: it })}
              onInactivar={(it) => setModal({ tipo: 'inactivar', item: it })}
            />
          )}
        </section>
      </div>

      {modal?.tipo === 'nuevo' && codigoSel && (
        <FormItemModal
          session={session} codigo={codigoSel}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); items.refresh(); cat.refresh(); }}
        />
      )}
      {modal?.tipo === 'editar' && codigoSel && (
        <FormItemModal
          session={session} codigo={codigoSel} item={modal.item}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); items.refresh(); }}
        />
      )}
      {modal?.tipo === 'inactivar' && codigoSel && (
        <InactivarItemModal
          session={session} codigo={codigoSel} item={modal.item}
          onClose={() => setModal(null)}
          onSuccess={() => { setModal(null); items.refresh(); }}
        />
      )}
    </GdShell>
  );
}

function ItemsCatalogo({ codigo, items, loading, error, puedeEditar, onAdd, onEditar, onInactivar }) {
  return (
    <div data-testid="cat-items">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--s-3)' }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>{codigo}</h2>
        {puedeEditar && (
          <button type="button" className="btn btn-accent btn-sm"
            onClick={onAdd}
            data-testid="cat-item-nuevo"
          >+ Nuevo ítem</button>
        )}
      </div>
      {loading && <p className="muted">Cargando ítems…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="empty" data-testid="cat-items-empty">
          <p>Sin ítems en este catálogo.</p>
        </div>
      )}
      {items.length > 0 && (
        <table className="data-table" data-testid="cat-items-table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Nombre</th>
              <th>Activo</th>
              {puedeEditar && <th>Acciones</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id || it.codigo} data-testid="cat-item-row">
                <td>{it.codigo || it.id}</td>
                <td>{it.nombre}</td>
                <td>
                  <span className={`badge ${it.activo !== false ? 'ok' : 'neutral'}`}>
                    {it.activo !== false ? 'Sí' : 'No'}
                  </span>
                </td>
                {puedeEditar && (
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button type="button" className="btn btn-secondary btn-sm"
                        onClick={() => onEditar(it)}
                        data-testid="cat-item-editar"
                      >Editar</button>
                      {it.activo !== false && (
                        <button type="button" className="btn btn-danger btn-sm"
                          onClick={() => onInactivar(it)}
                          data-testid="cat-item-inactivar"
                        >Inactivar</button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function FormItemModal({ session, codigo, item, onClose, onSuccess }) {
  const isEdit = Boolean(item);
  const [form, setForm] = useState({
    codigo: item?.codigo || '',
    nombre: item?.nombre || '',
    descripcion: item?.descripcion || '',
  });
  const crear = useCrearItemCatalogo(session);
  const editar = useActualizarItemCatalogo(session);
  const hook = isEdit ? editar : crear;

  async function handle() {
    try {
      if (isEdit) await editar.submit(codigo, item.id, form);
      else await crear.submit(codigo, form);
      onSuccess?.();
    } catch { /* hook */ }
  }
  const valid = form.codigo.trim().length >= 1 && form.nombre.trim().length >= 2;

  return (
    <ModalShell title={isEdit ? 'Editar ítem' : 'Nuevo ítem'} onClose={onClose} testid="cat-item-modal">
      <div className="field">
        <label>Código <span className="req">*</span></label>
        <input className="input" value={form.codigo}
          disabled={isEdit}
          onChange={(e) => setForm({ ...form, codigo: e.target.value })}
          data-testid="cat-item-codigo" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Nombre <span className="req">*</span></label>
        <input className="input" value={form.nombre}
          onChange={(e) => setForm({ ...form, nombre: e.target.value })}
          data-testid="cat-item-nombre" />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Descripción</label>
        <textarea className="textarea" rows={2} value={form.descripcion}
          onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          data-testid="cat-item-desc" />
      </div>
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-accent"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="cat-item-submit"
        >{hook.submitting ? 'Guardando…' : 'Guardar'}</button>
      </ModalFoot>
    </ModalShell>
  );
}

function InactivarItemModal({ session, codigo, item, onClose, onSuccess }) {
  const [motivo, setMotivo] = useState('');
  const [valid, setValid] = useState(false);
  const hook = useInactivarItemCatalogo(session);

  async function handle() {
    try {
      await hook.submit(codigo, item.id, motivo);
      onSuccess?.();
    } catch { /* hook */ }
  }

  return (
    <ModalShell title="Inactivar ítem" onClose={onClose} testid="cat-item-inactivar-modal">
      <p className="muted" style={{ fontSize: 13 }}>
        <strong>{item.nombre}</strong> dejará de aparecer en los selectores
        del sistema. Los registros existentes que lo usen se conservan.
      </p>
      <JustificacionRequiredField
        value={motivo}
        onChange={(v, ok) => { setMotivo(v); setValid(ok); }}
        label="Motivo de inactivación"
        id="cat-item-inact-motivo"
      />
      {hook.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{hook.error.message || 'Error.'}</div>
        </div>
      )}
      <ModalFoot onClose={onClose}>
        <button type="button" className="btn btn-danger-solid"
          disabled={!valid || hook.submitting} onClick={handle}
          data-testid="cat-item-inactivar-submit"
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
        style={{ width: 500, padding: 'var(--s-5)' }}>
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

export default AdminCatalogos;
