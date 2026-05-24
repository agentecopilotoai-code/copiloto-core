/**
 * CerrarExpedienteModal — GD-UI-0050. Cierre formal con acta + opción
 * de transferencia inmediata al Archivo Central.
 *
 * Integridad (RNF-009): genera acta de cierre server-side con hash
 * del índice consolidado. La UI muestra el acta resultante al
 * usuario y le permite descargarla.
 */
import React, { useState } from 'react';

import { JustificacionRequiredField } from '../components/JustificacionRequiredField.jsx';
import {
  useCerrarExpediente,
  useTransferirExpediente,
  useActaCierreExpediente,
} from './useGdExpedientes.js';

export function CerrarExpedienteModal({ session, expedienteId, onClose, onSuccess }) {
  const [acta, setActa] = useState('');
  const [motivo, setMotivo] = useState('');
  const [motivoValid, setMotivoValid] = useState(false);
  const [transferir, setTransferir] = useState(false);
  const [destino, setDestino] = useState('archivo_central');
  const [fase, setFase] = useState('form'); // form | cerrando | acta | listo

  const cerrar = useCerrarExpediente(session);
  const transfer = useTransferirExpediente(session);
  const actaCierre = useActaCierreExpediente(session, expedienteId, {
    enabled: fase === 'acta',
  });

  async function handle() {
    try {
      setFase('cerrando');
      await cerrar.submit(expedienteId, {
        acta_numero: acta,
        motivo,
      });
      if (transferir) {
        await transfer.submit(expedienteId, {
          destino, motivo,
        });
      }
      setFase('acta');
    } catch {
      setFase('form');
    }
  }

  function handleFinalizar() {
    setFase('listo');
    onSuccess?.();
  }

  const isValid = acta.trim().length >= 2 && motivoValid;
  const error = cerrar.error || transfer.error;

  return (
    <div
      role="dialog" aria-modal="true" data-testid="exp-cerrar-modal"
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.4)',
        display: 'grid', placeItems: 'center', zIndex: 50,
      }}
      onClick={onClose}
    >
      <div className="card" onClick={(e) => e.stopPropagation()}
        style={{ width: 560, padding: 'var(--s-5)' }}>
        <h2 style={{ marginTop: 0, fontSize: 16 }}>Cerrar expediente</h2>

        {fase === 'form' && (
          <>
            <p className="muted" style={{ fontSize: 13 }}>
              El cierre consolida el índice y los folios, genera el acta
              de cierre y bloquea cualquier modificación posterior. La
              acción es reversible solo mediante "Reabrir" con
              justificación.
            </p>

            <div className="field">
              <label>Número de acta de cierre <span className="req">*</span></label>
              <input
                className="input" value={acta}
                onChange={(e) => setActa(e.target.value)}
                placeholder="Acta 0023 / 2026"
                data-testid="exp-cerrar-acta"
              />
            </div>

            <div style={{ marginTop: 'var(--s-3)' }}>
              <JustificacionRequiredField
                value={motivo}
                onChange={(v, ok) => { setMotivo(v); setMotivoValid(ok); }}
                label="Motivo / contexto del cierre"
                id="exp-cerrar-motivo"
              />
            </div>

            <div style={{ marginTop: 'var(--s-3)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={transferir}
                  onChange={(e) => setTransferir(e.target.checked)}
                  data-testid="exp-cerrar-transferir"
                />
                Transferir inmediatamente al Archivo Central
              </label>
              {transferir && (
                <div className="field" style={{ marginTop: 8 }}>
                  <label>Destino</label>
                  <select
                    className="select"
                    value={destino}
                    onChange={(e) => setDestino(e.target.value)}
                    data-testid="exp-cerrar-destino"
                  >
                    <option value="archivo_central">Archivo Central</option>
                    <option value="archivo_historico">Archivo Histórico</option>
                  </select>
                </div>
              )}
            </div>

            {error && (
              <div className="alert danger" role="alert" style={{ marginTop: 12 }}>
                <div className="body">{error.message || 'No se pudo cerrar.'}</div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--s-2)', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancelar</button>
              <button
                type="button" className="btn btn-danger-solid"
                disabled={!isValid} onClick={handle}
                data-testid="exp-cerrar-submit"
              >Cerrar expediente</button>
            </div>
          </>
        )}

        {fase === 'cerrando' && (
          <p className="muted" data-testid="exp-cerrar-progress">
            Consolidando índice, generando acta y registrando cierre…
          </p>
        )}

        {fase === 'acta' && (
          <div data-testid="exp-cerrar-acta-preview">
            <p style={{ fontSize: 14 }}>
              <strong>✓ Expediente cerrado.</strong>{' '}
              {transferir && 'Transferencia registrada al Archivo Central.'}
            </p>
            {actaCierre.loading && <p className="muted">Recuperando acta…</p>}
            {actaCierre.data && (
              <div className="card" style={{ padding: 'var(--s-4)', background: 'var(--surface-subtle)', marginTop: 'var(--s-3)' }}>
                <p style={{ fontSize: 13, fontFamily: 'var(--font-serif)' }}>
                  Acta <strong>{actaCierre.data.numero}</strong> emitida el{' '}
                  {fmt(actaCierre.data.emitida_en)}.
                </p>
                <p className="muted" style={{ fontSize: 12 }}>
                  Hash del índice (SHA-256):{' '}
                  <code data-testid="exp-acta-hash">{actaCierre.data.hash_indice || '—'}</code>
                </p>
                {actaCierre.data.url_descarga && (
                  <a
                    className="btn btn-accent btn-sm"
                    href={actaCierre.data.url_descarga}
                    download
                    data-testid="exp-acta-descargar"
                  >Descargar acta</a>
                )}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--s-4)' }}>
              <button
                type="button" className="btn btn-accent"
                onClick={handleFinalizar}
                data-testid="exp-cerrar-finalizar"
              >Finalizar</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function fmt(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('es-CO'); }
  catch { return iso; }
}

export default CerrarExpedienteModal;
