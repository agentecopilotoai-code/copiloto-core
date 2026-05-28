/**
 * ComposerCorreoSaliente — GD-UI-0080.
 *
 * Composer de correo saliente con:
 *  - To/Cc/Bcc (chips por dirección)
 *  - Asunto
 *  - Selector de plantilla (auto-llena cuerpo)
 *  - Cuerpo (textarea con preview HTML)
 *  - Adjuntos (file input múltiple)
 *  - Asociar a radicado (opcional)
 *
 * Backend valida headers, DKIM, etc. — el composer es solo UI.
 */
import React, { useState } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { gdCanAny } from '../../../permissions/gd-matrix.js';
import {
  useCorreoComposer, usePlantillasCorreo,
} from './useGdCorreo.js';

export function ComposerCorreoSaliente({
  session, roles = [], onNavigate, radicadoAsociado = null, ...shellProps
}) {
  const tienePermiso = gdCanAny(roles, 'COR-EMAIL-003', 'RW');
  const c = useCorreoComposer(session);
  const plantillas = usePlantillasCorreo(session);
  const [form, setForm] = useState({
    para: '', cc: '', bcc: '', asunto: '',
    cuerpo_html: '', plantilla_id: '',
    radicado_asociado: radicadoAsociado,
  });
  const [enviado, setEnviado] = useState(null);

  function actualizar(k, v) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  function aplicarPlantilla(id) {
    actualizar('plantilla_id', id);
    const p = plantillas.items.find((x) => x.id === id);
    if (p) {
      setForm((f) => ({
        ...f, plantilla_id: id,
        asunto: f.asunto || p.asunto || '',
        cuerpo_html: p.cuerpo_html || '',
      }));
    }
  }

  function parsearEmails(s) {
    if (!s) return [];
    return s.split(/[,;]/).map((x) => x.trim()).filter(Boolean);
  }

  async function enviar(e) {
    e?.preventDefault?.();
    setEnviado(null);
    const para = parsearEmails(form.para);
    if (para.length === 0) {
      setEnviado({ ok: false, error: { message: 'Indica al menos un destinatario.' } });
      return;
    }
    try {
      const r = await c.submit({
        para,
        cc: parsearEmails(form.cc),
        bcc: parsearEmails(form.bcc),
        asunto: form.asunto,
        cuerpo_html: form.cuerpo_html,
        plantilla_id: form.plantilla_id || undefined,
        radicado_asociado: form.radicado_asociado || undefined,
      });
      setEnviado({ ok: true, msg: `Enviado (id: ${r?.id || '?'}).` });
    } catch (err) {
      setEnviado({ ok: false, error: err });
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Composer correo' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Composer de correo saliente</h1>
          <p className="subtitle">
            Compone un correo institucional. Usa plantillas
            corporativas para mantener firma y branding.
          </p>
        </div>
      </div>

      {!tienePermiso && (
        <div className="alert warn" role="alert"
          data-testid="cor-comp-no-perm"
        >
          <div className="body">No tienes permiso para enviar correos.</div>
        </div>
      )}

      {tienePermiso && (
        <form onSubmit={enviar} className="card"
          style={{ padding: 'var(--s-4)' }}
          data-testid="cor-comp-form"
        >
          {plantillas.items.length > 0 && (
            <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
              Plantilla
              <select value={form.plantilla_id}
                onChange={(e) => aplicarPlantilla(e.target.value)}
                style={{ width: '100%' }}
                data-testid="cor-comp-plantilla"
              >
                <option value="">— Ninguna —</option>
                {plantillas.items.map((p) => (
                  <option key={p.id} value={p.id}>{p.nombre}</option>
                ))}
              </select>
            </label>
          )}

          <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
            Para *
            <input type="text" required
              value={form.para}
              onChange={(e) => actualizar('para', e.target.value)}
              placeholder="a@b.com, c@d.com"
              style={{ width: '100%' }}
              data-testid="cor-comp-para"
            />
          </label>
          <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
            CC
            <input type="text"
              value={form.cc}
              onChange={(e) => actualizar('cc', e.target.value)}
              style={{ width: '100%' }}
              data-testid="cor-comp-cc"
            />
          </label>
          <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
            BCC
            <input type="text"
              value={form.bcc}
              onChange={(e) => actualizar('bcc', e.target.value)}
              style={{ width: '100%' }}
              data-testid="cor-comp-bcc"
            />
          </label>
          <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
            Asunto *
            <input type="text" required
              value={form.asunto}
              onChange={(e) => actualizar('asunto', e.target.value)}
              style={{ width: '100%' }}
              data-testid="cor-comp-asunto"
            />
          </label>
          <label style={{ display: 'block', marginBottom: 'var(--s-2)' }}>
            Cuerpo (HTML permitido)
            <textarea rows={10}
              value={form.cuerpo_html}
              onChange={(e) => actualizar('cuerpo_html', e.target.value)}
              style={{ width: '100%', fontFamily: 'monospace', fontSize: 13 }}
              data-testid="cor-comp-cuerpo"
            />
          </label>

          {form.cuerpo_html && (
            <details style={{ marginBottom: 'var(--s-3)' }}>
              <summary style={{ cursor: 'pointer', fontSize: 12 }}>
                Vista previa
              </summary>
              <div className="card"
                style={{ padding: 'var(--s-3)', marginTop: 'var(--s-1)' }}
                data-testid="cor-comp-preview"
                dangerouslySetInnerHTML={{ __html: form.cuerpo_html }}
              />
            </details>
          )}

          {form.radicado_asociado && (
            <div className="alert info" style={{ marginBottom: 'var(--s-2)' }}
              data-testid="cor-comp-radicado"
            >
              <div className="body">
                Asociado al radicado #{form.radicado_asociado}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 'var(--s-2)',
            justifyContent: 'flex-end' }}
          >
            <button type="submit" className="btn btn-primary"
              disabled={c.loading || !form.para || !form.asunto}
              data-testid="cor-comp-enviar"
            >{c.loading ? 'Enviando…' : 'Enviar'}</button>
          </div>

          {enviado && (
            <div className={`alert ${enviado.ok ? 'success' : 'danger'}`}
              role="status" style={{ marginTop: 'var(--s-3)' }}
              data-testid="cor-comp-feedback"
            >
              <div className="body">
                {enviado.ok ? enviado.msg : (enviado.error?.message || 'Error al enviar.')}
              </div>
            </div>
          )}
        </form>
      )}
    </GdShell>
  );
}

export default ComposerCorreoSaliente;
