/**
 * GenerarDocumento — GD-UI-0040. Genera documento desde plantilla.
 *
 * Renderiza form dinámico con las variables declaradas por la plantilla
 * + preview en vivo con sustitución `{{variable}}`. Al éxito navega a
 * la ficha del documento generado.
 */
import React, { useMemo, useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import {
  usePlantilla,
  useGenerarDocumentoDePlantilla,
} from './useGdPlantillas.js';
import { gdCanAny } from '../../../permissions/gd-matrix.js';

export function GenerarDocumento({
  session,
  roles = [],
  plantillaId,
  onNavigate,
  ...shellProps
}) {
  const { data: plantilla, loading, error } =
    usePlantilla(session, plantillaId);
  const hook = useGenerarDocumentoDePlantilla(session);
  const [valores, setValores] = useState({});
  const puedeGenerar = gdCanAny(roles, 'PLA-USE', 'R');

  const variables = plantilla?.variables || [];

  const preview = useMemo(() => {
    const base = plantilla?.cuerpo || '';
    return base.replace(/{{\s*([\w.-]+)\s*}}/g, (m, name) => {
      const v = valores[name];
      return v != null && String(v).length > 0 ? String(v) : m;
    });
  }, [plantilla, valores]);

  function update(name, value) {
    setValores((p) => ({ ...p, [name]: value }));
  }

  function todasCompletas() {
    return variables
      .filter((v) => v.requerida !== false)
      .every((v) => String(valores[v.nombre] || '').trim().length > 0);
  }

  async function handle() {
    try {
      const r = await hook.submit(plantillaId, valores);
      if (r?.id) {
        onNavigate?.(`/gd/documentos/${r.id}`);
      }
    } catch { /* hook */ }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Plantillas', path: '/gd/plantillas' },
        { label: 'Generar' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Generar documento</h1>
          <p className="subtitle">
            {plantilla
              ? <>Plantilla <strong>{plantilla.nombre}</strong> (v{plantilla.version_actual}).</>
              : 'Cargando plantilla…'}
          </p>
        </div>
      </div>

      {loading && <p className="muted">Cargando…</p>}
      {error && (
        <div className="alert danger" role="alert">
          <div className="body">{error.message || 'Error al cargar.'}</div>
        </div>
      )}

      {plantilla && !puedeGenerar && (
        <div className="alert warning" role="alert" data-testid="gen-no-perm">
          <div className="body">No tiene permisos para generar documentos a partir de plantillas.</div>
        </div>
      )}

      {plantilla && puedeGenerar && (
        <div
          data-testid="gen-layout"
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 'var(--s-4)',
          }}
        >
          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Variables</h3>
            {variables.length === 0 ? (
              <p className="muted" data-testid="gen-sin-vars">
                Esta plantilla no requiere variables.
              </p>
            ) : (
              <div data-testid="gen-vars-form">
                {variables.map((v) => (
                  <div className="field" key={v.nombre} style={{ marginBottom: 'var(--s-3)' }}>
                    <label>
                      {v.descripcion || v.nombre}
                      {v.requerida !== false && <span className="req"> *</span>}
                    </label>
                    {renderInput(v, valores[v.nombre], update)}
                  </div>
                ))}
              </div>
            )}

            {hook.error && (
              <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
                <div className="body">
                  {hook.error.message || 'No se pudo generar el documento.'}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => onNavigate?.('/gd/plantillas')}
                data-testid="gen-cancel"
              >Cancelar</button>
              <button
                type="button"
                className="btn btn-accent"
                disabled={!todasCompletas() || hook.submitting}
                onClick={handle}
                data-testid="gen-submit"
              >
                {hook.submitting ? 'Generando…' : 'Generar documento'}
              </button>
            </div>
          </div>

          <div className="card" style={{ padding: 'var(--s-5)' }}>
            <h3 style={{ fontSize: 14, marginTop: 0 }}>Vista previa</h3>
            <div
              data-testid="gen-preview"
              style={{
                background: 'var(--surface-alt)',
                padding: 'var(--s-4)',
                borderRadius: 'var(--r-md)',
                whiteSpace: 'pre-wrap',
                fontFamily: 'var(--font-serif)',
                fontSize: 13,
                lineHeight: 1.55,
                minHeight: 200,
              }}
            >
              {preview || <span className="muted">La plantilla no tiene cuerpo.</span>}
            </div>
          </div>
        </div>
      )}
    </GdShell>
  );
}

function renderInput(v, value, update) {
  const common = {
    value: value || '',
    onChange: (e) => update(v.nombre, e.target.value),
    'data-testid': `gen-var-${v.nombre}`,
  };
  if (v.tipo === 'fecha') {
    return <input type="date" className="input" {...common} />;
  }
  if (v.tipo === 'numero') {
    return <input type="number" className="input" {...common} />;
  }
  if (v.tipo === 'texto_largo') {
    return <textarea className="textarea" rows={4} {...common} />;
  }
  return <input type="text" className="input" {...common} />;
}

export default GenerarDocumento;
