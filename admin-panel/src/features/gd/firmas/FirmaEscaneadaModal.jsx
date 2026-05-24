/**
 * FirmaEscaneadaModal — GD-UI-0042. Registro de firma manuscrita escaneada.
 *
 * Sube la imagen de la firma (PNG/JPG, ≤2MB) + datos del firmante.
 * Útil para flujos transitorios mientras se adopta firma digital en
 * toda la entidad.
 */
import React, { useState } from 'react';

import { useRegistrarFirmaEscaneada } from './useGdFirmas.js';
import { subirArchivo } from '../services/gdApi.js';
import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';

const MIME_OK = ['image/png', 'image/jpeg'];
const MAX = 2 * 1024 * 1024; // 2 MB

export function FirmaEscaneadaModal({ session, documentoId, onClose, onSuccess }) {
  const [file, setFile] = useState(null);
  const [observacion, setObservacion] = useState('');
  const [obsValid, setObsValid] = useState(false);
  const [fileError, setFileError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const registrar = useRegistrarFirmaEscaneada(session);

  function pick(f) {
    setFileError(null);
    if (!f) { setFile(null); return; }
    if (!MIME_OK.includes(f.type)) {
      setFileError('Formato no permitido (use PNG o JPG).');
      return;
    }
    if (f.size > MAX) {
      setFileError('Archivo supera 2 MB.');
      return;
    }
    setFile(f);
  }

  async function handle() {
    try {
      setUploading(true);
      // 1) subir imagen
      const fd = await fileToBase64(file);
      const archivo = await subirArchivo(session, {
        nombre: file.name, mime: file.type, contenido_base64: fd,
        clase: 'firma_escaneada',
      });
      // 2) registrar firma
      await registrar.submit(documentoId, {
        archivo_firma_id: archivo.id,
        observacion,
      });
      onSuccess?.();
    } catch {
      /* hook captures error */
    } finally {
      setUploading(false);
    }
  }

  const isValid = file && obsValid && !fileError;

  return (
    <div
      className="modal-overlay" role="dialog" aria-modal="true"
      data-testid="firma-escaneada-modal"
    >
      <div className="modal-panel" style={{ maxWidth: 520 }}>
        <header className="modal-head">
          <h2>Registrar firma escaneada</h2>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Cerrar">×</button>
        </header>
        <div className="modal-body">
          <p className="muted" style={{ fontSize: 13 }}>
            La firma escaneada queda asociada al documento con su evidencia
            de hash, IP y fecha. Use firma digital cuando esté disponible.
          </p>
          <div className="field">
            <label>Imagen de la firma (PNG / JPG, máx 2 MB) <span className="req">*</span></label>
            <input
              type="file"
              accept="image/png,image/jpeg"
              onChange={(e) => pick(e.target.files?.[0])}
              data-testid="firma-escaneada-file"
            />
            {file && (
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }} data-testid="firma-escaneada-filename">
                {file.name} · {(file.size / 1024).toFixed(0)} KB
              </div>
            )}
            {fileError && (
              <div className="muted" style={{ color: 'var(--danger)', fontSize: 12, marginTop: 4 }} data-testid="firma-escaneada-fileerr">
                {fileError}
              </div>
            )}
          </div>
          <div style={{ marginTop: 'var(--s-3)' }}>
            <JustificacionRequiredField
              value={observacion}
              onChange={(v, ok) => { setObservacion(v); setObsValid(ok); }}
              label="Observación / contexto"
              id="firma-escaneada-obs"
            />
          </div>
          {registrar.error && (
            <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
              <div className="body">{registrar.error.message || 'Error al registrar.'}</div>
            </div>
          )}
        </div>
        <footer className="modal-foot">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button
            type="button"
            className="btn btn-accent"
            disabled={!isValid || uploading || registrar.submitting}
            onClick={handle}
            data-testid="firma-escaneada-submit"
          >
            {uploading || registrar.submitting ? 'Procesando…' : 'Registrar firma'}
          </button>
        </footer>
      </div>
    </div>
  );
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const s = String(r.result || '');
      const i = s.indexOf(',');
      resolve(i >= 0 ? s.slice(i + 1) : s);
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export default FirmaEscaneadaModal;
