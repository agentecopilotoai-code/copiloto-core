/**
 * NuevoRadicadoEntrada — wizard de 5 pasos para GD-UI-0007.
 *
 * Pasos:
 *  1. Canal y remitente (Tercero existente o crear inline)
 *  2. Asunto + descripción + sugerencia IA opcional inline
 *  3. Anexos (drag & drop con validación MIME/size)
 *  4. Clasificación inicial (sugerida por IA, editable)
 *  5. Confirmación — muestra numero_radicado + QR
 *
 * Sigue las convenciones del UI_BACKLOG:
 *  - Lenguaje formal ("Se ha radicado", no "¡Listo!").
 *  - Sin PII en URL (todos los IDs son UUID).
 *  - Sugerencias IA inline con [Aceptar / Modificar / Rechazar].
 */
import React, { useState, useCallback } from 'react';

import { GdShell } from '../shell/GdShell.jsx';
import { useCrearRadicadoEntrada } from './useGdRadicados.js';
import { RadicadoConstanciaPreview } from './RadicadoConstanciaPreview.jsx';

const STEP_LABELS = [
  'Canal y remitente',
  'Asunto y descripción',
  'Anexos',
  'Clasificación inicial',
  'Confirmación',
];

const TIPOS_CLASIFICACION = [
  { value: 'pqrsd', label: 'PQRSD (Petición/Queja/Reclamo/Sugerencia/Denuncia)' },
  { value: 'correspondencia_externa', label: 'Correspondencia externa' },
  { value: 'tramite', label: 'Trámite institucional' },
  { value: 'expediente', label: 'Expediente' },
];

export function NuevoRadicadoEntrada({
  session,
  canales = [],
  onNavigate,
  onTerceroSearch,
  onTerceroCrear,
  onSugerenciaIa,
  ...shellProps
}) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    canal_id: '',
    tercero_id: '',
    tercero_nuevo: null,
    asunto: '',
    descripcion: '',
    anexos: [],
    tipo_clasificacion: '',
    sub_tipo: '',
    dependencia_destino_id: '',
    sugerencia_ia: null,
  });

  const { submitting, error, radicado, submit } =
    useCrearRadicadoEntrada(session);

  const updateField = useCallback((k, v) => {
    setForm((prev) => ({ ...prev, [k]: v }));
  }, []);

  const next = () => setStep((s) => Math.min(s + 1, 5));
  const prev = () => setStep((s) => Math.max(s - 1, 1));

  const canAdvance = stepCanAdvance(step, form);

  async function handleSubmit() {
    const payload = {
      canal_id: form.canal_id,
      tercero_id: form.tercero_id || undefined,
      tercero_nuevo: form.tercero_nuevo || undefined,
      asunto: form.asunto,
      descripcion: form.descripcion,
      anexos: form.anexos.map((a) => a.id || a.archivo_id).filter(Boolean),
      clasificacion_sugerida: form.tipo_clasificacion
        ? {
            tipo_clasificacion: form.tipo_clasificacion,
            sub_tipo: form.sub_tipo || undefined,
            dependencia_destino_id: form.dependencia_destino_id || undefined,
          }
        : undefined,
      sugerencia_ia_id: form.sugerencia_ia?.id,
    };
    try {
      await submit(payload);
      setStep(5);
    } catch {
      /* el error queda en `error` del hook y se muestra abajo */
    }
  }

  return (
    <GdShell
      {...shellProps}
      breadcrumbs={[
        { label: 'Gestión Documental', path: '/gd' },
        { label: 'Ventanilla', path: '/gd/ventanilla' },
        { label: 'Nuevo radicado de entrada' },
      ]}
    >
      <div className="page-head">
        <div className="title-block">
          <h1>Nuevo radicado de entrada</h1>
          <p className="subtitle">
            Paso {Math.min(step, 5)} de 5 · {STEP_LABELS[Math.min(step, 5) - 1]}
          </p>
        </div>
      </div>

      <StepperBar step={step} labels={STEP_LABELS} />

      <div
        className="card"
        data-testid="nuevo-radicado-step"
        data-step={step}
        style={{ marginTop: 'var(--s-5)', padding: 'var(--s-6)' }}
      >
        {step === 1 && (
          <Step1Canal
            form={form}
            updateField={updateField}
            canales={canales}
            onTerceroSearch={onTerceroSearch}
            onTerceroCrear={onTerceroCrear}
          />
        )}
        {step === 2 && (
          <Step2Asunto
            form={form}
            updateField={updateField}
            onSugerenciaIa={onSugerenciaIa}
          />
        )}
        {step === 3 && <Step3Anexos form={form} updateField={updateField} />}
        {step === 4 && <Step4Clasificacion form={form} updateField={updateField} />}
        {step === 5 && (
          <Step5Confirmacion radicado={radicado} onNavigate={onNavigate} />
        )}

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            <div className="body">
              <div className="title">No se pudo radicar.</div>
              <div>
                {error.body?.detail?.message ||
                  error.message ||
                  'Intente nuevamente. Si persiste, contacte al administrador.'}
              </div>
            </div>
          </div>
        )}
      </div>

      {step < 5 && (
        <div
          className="wizard-foot"
          style={{
            display: 'flex',
            gap: 'var(--s-3)',
            marginTop: 'var(--s-5)',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <button
            type="button"
            className="btn btn-secondary"
            onClick={prev}
            disabled={step === 1}
            data-testid="wizard-prev"
          >
            Anterior
          </button>
          <span className="muted">{progressText(step, form)}</span>
          {step < 4 ? (
            <button
              type="button"
              className="btn btn-accent"
              onClick={next}
              disabled={!canAdvance}
              data-testid="wizard-next"
            >
              Continuar
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={submitting || !canAdvance}
              data-testid="wizard-submit"
            >
              {submitting ? 'Radicando…' : 'Radicar entrada'}
            </button>
          )}
        </div>
      )}
    </GdShell>
  );
}

function StepperBar({ step, labels }) {
  return (
    <div className="wizard-bar" data-testid="stepper-bar">
      {labels.map((label, idx) => {
        const num = idx + 1;
        const state = num < step ? 'done' : num === step ? 'active' : 'pending';
        return (
          <div key={label} className={`wizard-step ${state}`} data-step-state={state}>
            <span className="step-num" aria-hidden="true">{num}</span>
            <span className="step-text">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

function Step1Canal({ form, updateField, canales, onTerceroSearch, onTerceroCrear }) {
  const [creandoTercero, setCreandoTercero] = useState(false);
  const [busqueda, setBusqueda] = useState('');
  const [resultados, setResultados] = useState([]);

  async function handleBuscar(q) {
    setBusqueda(q);
    if (q.length < 2 || !onTerceroSearch) {
      setResultados([]);
      return;
    }
    try {
      const r = await onTerceroSearch(q);
      setResultados(Array.isArray(r) ? r : (r?.items || []));
    } catch {
      setResultados([]);
    }
  }

  return (
    <div>
      <h2 style={{ fontSize: 17, marginTop: 0 }}>Canal de recepción</h2>
      <div className="field" style={{ maxWidth: 360, marginBottom: 'var(--s-6)' }}>
        <label htmlFor="canal">Canal <span className="req">*</span></label>
        <select
          id="canal"
          className="select"
          value={form.canal_id}
          onChange={(e) => updateField('canal_id', e.target.value)}
          data-testid="canal-select"
        >
          <option value="">Seleccione un canal…</option>
          {canales.map((c) => (
            <option key={c.id} value={c.id}>{c.nombre}</option>
          ))}
        </select>
      </div>

      <h2 style={{ fontSize: 17 }}>Remitente</h2>
      {!creandoTercero ? (
        <>
          <div className="field" style={{ marginBottom: 'var(--s-3)' }}>
            <label>Buscar tercero (cédula, NIT, nombre o correo)</label>
            <input
              type="search"
              className="input"
              placeholder="Buscar…"
              value={busqueda}
              onChange={(e) => handleBuscar(e.target.value)}
              data-testid="tercero-search"
            />
            <span className="hint">
              Mínimo 2 caracteres. Si no encuentra el tercero, puede
              crearlo en línea.
            </span>
          </div>
          {resultados.length > 0 && (
            <ul
              data-testid="tercero-results"
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--r-md)',
                maxHeight: 220, overflow: 'auto',
              }}
            >
              {resultados.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    className={`tercero-option ${form.tercero_id === t.id ? 'selected' : ''}`}
                    onClick={() => updateField('tercero_id', t.id)}
                    style={{
                      width: '100%', textAlign: 'left',
                      padding: 'var(--s-3) var(--s-4)', border: 0,
                      background: form.tercero_id === t.id
                        ? 'var(--sky-50)' : 'transparent',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{t.nombre_completo}</div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {t.tipo_doc_identidad} {t.numero_doc_identidad}
                      {t.correo_electronico && ` · ${t.correo_electronico}`}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setCreandoTercero(true)}
            style={{ marginTop: 'var(--s-3)' }}
            data-testid="tercero-crear-toggle"
          >
            + Crear tercero nuevo
          </button>
        </>
      ) : (
        <TerceroInlineForm
          onCreate={async (payload) => {
            const created = onTerceroCrear ? await onTerceroCrear(payload) : payload;
            updateField('tercero_nuevo', null);
            updateField('tercero_id', created.id || '');
            setCreandoTercero(false);
          }}
          onCancel={() => setCreandoTercero(false)}
        />
      )}
    </div>
  );
}

function TerceroInlineForm({ onCreate, onCancel }) {
  const [tipo, setTipo] = useState('CC');
  const [numero, setNumero] = useState('');
  const [nombre, setNombre] = useState('');
  const [correo, setCorreo] = useState('');

  return (
    <div data-testid="tercero-inline-form">
      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 'var(--s-3)' }}>
        <div className="field">
          <label>Tipo</label>
          <select
            className="select"
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
          >
            <option value="CC">CC</option>
            <option value="CE">CE</option>
            <option value="TI">TI</option>
            <option value="NIT">NIT</option>
            <option value="PAS">Pasaporte</option>
          </select>
        </div>
        <div className="field">
          <label>Documento <span className="req">*</span></label>
          <input
            className="input"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
            data-testid="tercero-numero"
          />
        </div>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Nombre completo <span className="req">*</span></label>
        <input
          className="input"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          data-testid="tercero-nombre"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label>Correo electrónico</label>
        <input
          type="email"
          className="input"
          value={correo}
          onChange={(e) => setCorreo(e.target.value)}
        />
      </div>
      <div style={{ display: 'flex', gap: 'var(--s-2)', marginTop: 'var(--s-4)' }}>
        <button
          type="button"
          className="btn btn-accent"
          onClick={() => onCreate({
            tipo_doc_identidad: tipo,
            numero_doc_identidad: numero,
            nombre_completo: nombre,
            correo_electronico: correo || null,
          })}
          disabled={!numero || !nombre}
          data-testid="tercero-crear-submit"
        >
          Crear y seleccionar
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

function Step2Asunto({ form, updateField, onSugerenciaIa }) {
  const [sugerenciaLoading, setSugerenciaLoading] = useState(false);

  async function pedirSugerencia() {
    if (!onSugerenciaIa) return;
    setSugerenciaLoading(true);
    try {
      const s = await onSugerenciaIa({
        asunto: form.asunto,
        descripcion: form.descripcion,
      });
      updateField('sugerencia_ia', s);
      if (s?.resumen) updateField('descripcion', s.resumen);
    } catch {
      /* no-op */
    } finally {
      setSugerenciaLoading(false);
    }
  }

  return (
    <div>
      <h2 style={{ fontSize: 17, marginTop: 0 }}>Asunto y descripción</h2>
      <div className="field">
        <label htmlFor="asunto">Asunto <span className="req">*</span></label>
        <input
          id="asunto"
          className="input"
          value={form.asunto}
          onChange={(e) => updateField('asunto', e.target.value)}
          maxLength={500}
          data-testid="asunto-input"
        />
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label htmlFor="descripcion">Descripción</label>
        <textarea
          id="descripcion"
          className="textarea"
          rows={5}
          value={form.descripcion}
          onChange={(e) => updateField('descripcion', e.target.value)}
          maxLength={4000}
          data-testid="descripcion-input"
        />
      </div>
      {onSugerenciaIa && (
        <div
          className="alert info"
          style={{ marginTop: 'var(--s-4)' }}
          data-testid="sugerencia-ia-box"
        >
          <div className="body">
            <div className="title">Sugerencia IA opcional</div>
            <div>
              La IA puede ayudar a redactar un resumen más claro a partir
              del texto ingresado. La decisión final es del operador.
            </div>
            {form.sugerencia_ia ? (
              <div style={{ marginTop: 8 }}>
                <strong>Resumen sugerido:</strong> {form.sugerencia_ia.resumen}
                <div style={{ marginTop: 6, display: 'flex', gap: 'var(--s-2)' }}>
                  <button
                    type="button"
                    className="btn btn-sm btn-accent"
                    onClick={() => updateField('descripcion', form.sugerencia_ia.resumen)}
                    data-testid="ia-aceptar"
                  >
                    Aceptar
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-secondary"
                    onClick={() => updateField('sugerencia_ia', null)}
                    data-testid="ia-rechazar"
                  >
                    Rechazar
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={pedirSugerencia}
                disabled={sugerenciaLoading || !form.asunto}
                style={{ marginTop: 8 }}
                data-testid="ia-pedir"
              >
                {sugerenciaLoading ? 'Consultando…' : 'Pedir sugerencia'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Step3Anexos({ form, updateField }) {
  const MAX_BYTES = 20 * 1024 * 1024; // 20 MB por archivo (RNF antivirus + tamaño)
  const ACCEPTED = /\.(pdf|docx?|xlsx?|jpe?g|png|gif|tiff?|odt|ods)$/i;

  function handleFiles(fileList) {
    const arr = Array.from(fileList || []);
    const valid = arr.filter(
      (f) => ACCEPTED.test(f.name) && f.size <= MAX_BYTES,
    );
    const stubs = valid.map((f) => ({
      id: `tmp-${f.name}-${f.size}`,
      nombre: f.name, size: f.size, mime_type: f.type,
    }));
    updateField('anexos', [...form.anexos, ...stubs]);
  }

  function remove(id) {
    updateField('anexos', form.anexos.filter((a) => a.id !== id));
  }

  return (
    <div>
      <h2 style={{ fontSize: 17, marginTop: 0 }}>Anexos</h2>
      <div
        className="empty"
        data-testid="anexos-dropzone"
        onDragOver={(e) => { e.preventDefault(); }}
        onDrop={(e) => {
          e.preventDefault();
          handleFiles(e.dataTransfer?.files);
        }}
        style={{ padding: 'var(--s-6)', cursor: 'pointer' }}
      >
        <p>
          Arrastre archivos aquí o{' '}
          <label
            style={{
              textDecoration: 'underline',
              color: 'var(--accent-base)',
              cursor: 'pointer',
            }}
          >
            seleccione del equipo
            <input
              type="file"
              multiple
              hidden
              accept=".pdf,.docx,.xlsx,.jpeg,.jpg,.png,.gif,.tiff,.odt,.ods"
              onChange={(e) => handleFiles(e.target.files)}
              data-testid="anexos-file-input"
            />
          </label>
        </p>
        <span className="hint">
          Formatos aceptados: PDF, Word, Excel, imágenes. Tamaño máximo 20 MB
          por archivo.
        </span>
      </div>
      {form.anexos.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, marginTop: 'var(--s-4)' }}>
          {form.anexos.map((a) => (
            <li
              key={a.id}
              data-testid="anexo-item"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--s-3)',
                padding: '6px 10px',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--r-md)',
                marginBottom: 6,
              }}
            >
              <span style={{ flex: 1 }}>{a.nombre}</span>
              <span className="muted" style={{ fontSize: 12 }}>
                {Math.round(a.size / 1024)} KB
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => remove(a.id)}
                aria-label={`Quitar ${a.nombre}`}
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Step4Clasificacion({ form, updateField }) {
  return (
    <div>
      <h2 style={{ fontSize: 17, marginTop: 0 }}>Clasificación inicial</h2>
      <div className="field">
        <label htmlFor="tipo">Tipo de clasificación <span className="req">*</span></label>
        <select
          id="tipo"
          className="select"
          value={form.tipo_clasificacion}
          onChange={(e) => updateField('tipo_clasificacion', e.target.value)}
          data-testid="tipo-clasificacion-select"
        >
          <option value="">Seleccione…</option>
          {TIPOS_CLASIFICACION.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginTop: 'var(--s-3)' }}>
        <label htmlFor="sub-tipo">Sub-tipo (opcional)</label>
        <input
          id="sub-tipo"
          className="input"
          placeholder="Ej. Petición de interés general"
          value={form.sub_tipo}
          onChange={(e) => updateField('sub_tipo', e.target.value)}
        />
      </div>
      <p className="hint" style={{ marginTop: 'var(--s-3)' }}>
        La derivación a dependencia se asigna automáticamente al confirmar,
        según las reglas configuradas por el administrador.
      </p>
    </div>
  );
}

function Step5Confirmacion({ radicado, onNavigate }) {
  if (!radicado) {
    return <p className="muted">Procesando radicación…</p>;
  }
  return (
    <div data-testid="step-confirmacion">
      <div className="alert success" role="status" style={{ marginBottom: 'var(--s-5)' }}>
        <div className="body">
          <div className="title">Radicación exitosa.</div>
          <div>
            Se ha radicado el documento con número{' '}
            <strong>{radicado.numero_radicado}</strong>. La constancia
            de radicación puede descargarse a continuación.
          </div>
        </div>
      </div>
      <RadicadoConstanciaPreview radicado={radicado} />
      <div style={{ display: 'flex', gap: 'var(--s-3)', marginTop: 'var(--s-5)' }}>
        <button
          type="button"
          className="btn btn-accent"
          onClick={() => onNavigate?.(`/gd/ventanilla/radicados/${radicado.id}`)}
          data-testid="ir-ficha"
        >
          Ir a la ficha
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => onNavigate?.('/gd/ventanilla/nuevo-entrada')}
        >
          Radicar otro
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => window.print && window.print()}
        >
          Imprimir constancia
        </button>
      </div>
    </div>
  );
}

function stepCanAdvance(step, form) {
  switch (step) {
    case 1: return Boolean(form.canal_id && (form.tercero_id || form.tercero_nuevo));
    case 2: return form.asunto.trim().length >= 2;
    case 3: return true; // anexos opcionales
    case 4: return Boolean(form.tipo_clasificacion);
    default: return true;
  }
}

function progressText(step, form) {
  const totalPasos = 5;
  const completos = step - 1;
  return `Progreso ${completos}/${totalPasos - 1}${
    form.anexos.length ? ` · ${form.anexos.length} anexo(s)` : ''
  }`;
}

export default NuevoRadicadoEntrada;
