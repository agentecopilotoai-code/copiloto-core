/**
 * PlantillasNotificacion — GD-UI-0060. Plantillas de email/SMS.
 *
 * Variables disponibles ({{nombre}}, {{numero_radicado}}, etc) y
 * permite "Probar" enviando a una dirección de prueba. NOT-TPL.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  usePlantillasNotificacion,
  useActualizarPlantillaNotificacion,
  useProbarPlantillaNotificacion,
} from './useGdAdmin.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function PlantillasNotificacion({ session, roles = [], ...shellProps }) {
  const { items, loading, error, refresh } = usePlantillasNotificacion(session);
  const [sel, setSel] = useState(null);
  const puedeEditar = gdCanAny(roles, 'NOT-TPL', 'RW');

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Plantillas de notificación' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Plantillas de notificación</h1>
          <p className="subtitle">
            {items.length} plantilla(s) (email + SMS) para notificaciones
            automáticas del sistema.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-secondary"
            onClick={refresh}
            data-testid="not-refresh"
          >Actualizar</button>
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error.'}</div>
        </div>
      )}

      <div data-testid="not-layout" style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 'var(--s-4)' }}>
        <aside className="card" style={{ padding: 0 }}>
          {!loading && !error && items.length === 0 && (
            <div className="empty" data-testid="not-empty"><p>Sin plantillas.</p></div>
          )}
          {items.map((p) => (
            <button
              key={p.codigo}
              type="button"
              data-testid="not-row"
              onClick={() => setSel(p)}
              style={{
                display: 'block', width: '100%', textAlign: 'left',
                padding: 'var(--s-3)',
                border: 0,
                borderBottom: '1px solid var(--border-subtle)',
                background: sel?.codigo === p.codigo ? 'var(--sky-50)' : 'transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13 }}>{p.nombre || p.codigo}</div>
              <div className="muted" style={{ fontSize: 11 }}>
                {p.canal} · v{p.version_actual || 1}
              </div>
            </button>
          ))}
        </aside>
        <section className="card" style={{ padding: 'var(--s-5)' }}>
          {!sel && <p className="muted">Seleccione una plantilla.</p>}
          {sel && puedeEditar && (
            <EditorPlantilla
              key={sel.codigo}
              session={session} plantilla={sel}
              onSaved={() => refresh()}
            />
          )}
          {sel && !puedeEditar && (
            <PreviewPlantilla plantilla={sel} />
          )}
        </section>
      </div>
    </GdShell>
  );
}

function EditorPlantilla({ session, plantilla, onSaved }) {
  const [form, setForm] = useState({
    asunto: plantilla.asunto || '',
    cuerpo: plantilla.cuerpo || '',
  });
  const [emailPrueba, setEmailPrueba] = useState('');
  const [probarInfo, setProbarInfo] = useState(null);
  const editar = useActualizarPlantillaNotificacion(session);
  const probar = useProbarPlantillaNotificacion(session);

  async function handleGuardar() {
    try {
      await editar.submit(plantilla.codigo, form);
      onSaved?.();
    } catch { /* hook */ }
  }
  async function handleProbar() {
    setProbarInfo(null);
    try {
      const r = await probar.submit(plantilla.codigo, { destinatario: emailPrueba });
      setProbarInfo({ ok: true, ...r });
    } catch (err) {
      setProbarInfo({ ok: false, error: err });
    }
  }

  return (
    <div data-testid="not-editor">
      <h2 style={{ fontSize: 16, marginTop: 0 }}>
        {plantilla.nombre || plantilla.codigo}
      </h2>
      {(plantilla.variables || []).length > 0 && (
        <p className="muted" style={{ fontSize: 12 }}>
          Variables disponibles:{' '}
          {plantilla.variables.map((v) => (
            <code key={v} style={{ marginRight: 4 }}>{`{{${v}}}`}</code>
          ))}
        </p>
      )}
      {plantilla.canal === 'email' && (
        <div className="field">
          <label>Asunto</label>
          <input className="input" value={form.asunto}
            onChange={(e) => setForm({ ...form, asunto: e.target.value })}
            data-testid="not-asunto"
          />
        </div>
      )}
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Cuerpo</label>
        <textarea className="textarea" rows={10} value={form.cuerpo}
          onChange={(e) => setForm({ ...form, cuerpo: e.target.value })}
          data-testid="not-cuerpo"
        />
      </div>
      {editar.error && (
        <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
          <div className="body">{editar.error.message || 'Error.'}</div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn btn-accent"
          disabled={editar.submitting} onClick={handleGuardar}
          data-testid="not-guardar"
        >{editar.submitting ? 'Guardando…' : 'Guardar'}</button>
      </div>

      <hr style={{ margin: 'var(--s-5) 0' }} />

      <h3 style={{ fontSize: 14 }}>Enviar prueba</h3>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <div className="field" style={{ flex: 1 }}>
          <label>Destinatario de prueba</label>
          <input
            className="input" value={emailPrueba}
            onChange={(e) => setEmailPrueba(e.target.value)}
            placeholder="correo@entidad.gov.co"
            data-testid="not-prueba-dest"
          />
        </div>
        <button type="button" className="btn btn-secondary"
          disabled={probar.submitting || !emailPrueba} onClick={handleProbar}
          data-testid="not-probar"
        >{probar.submitting ? 'Enviando…' : 'Enviar prueba'}</button>
      </div>
      {probarInfo && (
        <div
          className={`alert ${probarInfo.ok ? 'success' : 'danger'}`}
          role="status"
          data-testid="not-prueba-info"
          style={{ marginTop: 12 }}
        >
          <div className="body">
            {probarInfo.ok
              ? 'Envío de prueba encolado.'
              : `Error: ${probarInfo.error?.message || 'desconocido'}`}
          </div>
        </div>
      )}
    </div>
  );
}

function PreviewPlantilla({ plantilla }) {
  return (
    <div data-testid="not-preview">
      <h2 style={{ fontSize: 16, marginTop: 0 }}>{plantilla.nombre}</h2>
      {plantilla.asunto && (
        <p><strong>Asunto:</strong> {plantilla.asunto}</p>
      )}
      <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font-serif)' }}>
        {plantilla.cuerpo || '(sin cuerpo)'}
      </pre>
    </div>
  );
}

export default PlantillasNotificacion;
