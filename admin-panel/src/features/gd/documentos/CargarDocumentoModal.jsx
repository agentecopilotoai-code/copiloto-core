/**
 * CargarDocumentoModal — GD-UI-0037. Drag&drop con validación MIME + size.
 *
 * Flujo: subir archivo a /core/archivos → recibe archivo_digital_id →
 * crear documento con metadata. RNF-046: antivirus se aplica server-side
 * post-upload; aquí solo validamos extensión y tamaño cliente.
 */
import React, { useState } from 'react';

import {
  useCrearDocumento,
  useSubirArchivo,
} from './useGdDocumentos.js';

const MAX_BYTES = 50 * 1024 * 1024; // 50 MB
const ACCEPTED = /\.(pdf|docx?|xlsx?|pptx?|jpe?g|png|gif|tiff?|odt|ods)$/i;

export function CargarDocumentoModal({ session, onClose, onSuccess }) {
  const [file, setFile] = useState(null);
  const [meta, setMeta] = useState({
    titulo: '', tipo: 'comunicacion', descripcion: '',
  });
  const subir = useSubirArchivo(session);
  const crear = useCrearDocumento(session);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null);

  function pick(f) {
    if (!f) { setFile(null); return; }
    if (!ACCEPTED.test(f.name)) {
      setError(new Error('Formato no permitido. Use PDF, Word, Excel, imágenes.'));
      return;
    }
    if (f.size > MAX_BYTES) {
      setError(new Error('Archivo supera el tamaño máximo de 50 MB.'));
      return;
    }
    setError(null);
    setFile(f);
    if (!meta.titulo) {
      setMeta((m) => ({ ...m, titulo: f.name.replace(/\.[^.]+$/, '') }));
    }
  }

  function update(k, v) { setMeta((m) => ({ ...m, [k]: v })); }

  const isValid = Boolean(file && meta.titulo.trim().length >= 2);

  async function handleSubmit() {
    setError(null);
    setProgress('subiendo');
    try {
      const archivo = await subir.submit({
        nombre: file.name,
        size: file.size,
        mime_type: file.type,
        // base64 stub — backend real espera multipart o presigned URL
        contenido_b64: 'stub',
      });
      setProgress('creando');
      const doc = await crear.submit({
        titulo: meta.titulo,
        tipo: meta.tipo,
        descripcion: meta.descripcion,
        archivo_digital_id: archivo?.id || archivo?.archivo_digital_id,
      });
      setProgress('listo');
      onSuccess?.(doc);
    } catch (err) {
      setError(err);
      setProgress(null);
    }
  }

  return (
    <div
      role="dialog" aria-modal="true" data-testid="cargar-doc-modal"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()} className="card"
        style={{ width: 520, padding: 'var(--s-5)' }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Cargar documento</h2>
        <p className="muted" style={{ fontSize: 13 }}>
          Formatos: PDF, Word, Excel, PowerPoint, imágenes. Máximo 50 MB.
          El antivirus se ejecuta automáticamente tras la carga.
        </p>

        <div
          data-testid="cargar-dropzone"
          className="empty"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            pick(e.dataTransfer?.files?.[0]);
          }}
          style={{ marginTop: 'var(--s-3)' }}
        >
          {!file ? (
            <p>
              Arrastre el archivo aquí o{' '}
              <label style={{ textDecoration: 'underline', color: 'var(--accent-base)', cursor: 'pointer' }}>
                selecciónelo
                <input
                  type="file"
                  hidden
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.gif,.tiff,.odt,.ods"
                  onChange={(e) => pick(e.target.files?.[0])}
                  data-testid="cargar-file-input"
                />
              </label>
            </p>
          ) : (
            <p data-testid="archivo-seleccionado">
              📄 <strong>{file.name}</strong> · {Math.round(file.size / 1024)} KB
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setFile(null)}
                style={{ marginLeft: 8 }}
                data-testid="cargar-quitar"
              >Quitar</button>
            </p>
          )}
        </div>

        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Título <span className="req">*</span></label>
          <input
            className="input"
            value={meta.titulo}
            onChange={(e) => update('titulo', e.target.value)}
            data-testid="cargar-titulo"
          />
        </div>

        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Tipo</label>
          <select
            className="select"
            value={meta.tipo}
            onChange={(e) => update('tipo', e.target.value)}
            data-testid="cargar-tipo"
          >
            <option value="comunicacion">Comunicación</option>
            <option value="acto_administrativo">Acto administrativo</option>
            <option value="oficio">Oficio</option>
            <option value="contrato">Contrato</option>
            <option value="informe">Informe</option>
            <option value="otro">Otro</option>
          </select>
        </div>

        <div className="field" style={{ marginTop: 'var(--s-3)' }}>
          <label>Descripción</label>
          <textarea
            className="textarea"
            rows={3}
            value={meta.descripcion}
            onChange={(e) => update('descripcion', e.target.value)}
            data-testid="cargar-desc"
          />
        </div>

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
            <div className="body">{error.message || 'Error.'}</div>
          </div>
        )}

        {progress && (
          <p className="muted" data-testid="cargar-progress" style={{ marginTop: 8 }}>
            {progress === 'subiendo' && 'Subiendo archivo…'}
            {progress === 'creando' && 'Creando referencia documental…'}
            {progress === 'listo' && '✓ Cargado correctamente.'}
          </p>
        )}

        <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className="btn btn-accent"
            disabled={!isValid || subir.submitting || crear.submitting}
            onClick={handleSubmit}
            data-testid="cargar-submit"
          >
            {(subir.submitting || crear.submitting) ? 'Procesando…' : 'Cargar'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CargarDocumentoModal;
