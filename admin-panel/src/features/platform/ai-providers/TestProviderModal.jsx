/**
 * Modal "Probar" del provider por modalidad (transversal).
 *
 * Cada modalidad tiene su propio form (input) y render de output:
 *   - LLM   → prompt (+ system opcional)             → texto generado
 *   - Image → prompt (+ aspect_ratio)                → preview de imagen
 *   - Video → prompt (+ aspect_ratio, duration)      → preview de video
 *   - TTS   → text (+ voice_tone, language)          → audio reproducible
 *   - STT   → file upload (audio)                    → transcript
 *
 * El backend devuelve un envelope uniforme: `{ok, output: {kind, ...}}`.
 * Cuando `ok=false`, mostramos el `error_class` + `error` granular
 * (rate-limited, content-filter, timeout, etc.) sin opacarlo con un toast.
 */
import { useState } from 'react';

import {
  AlertBanner,
  Button,
  FormField,
  Modal,
  StatusBadge,
} from '../../../components/ui/index.js';
import { modalityLabel, providerLabel } from './aiProvidersData.js';
import styles from './AIProviders.module.css';


export function TestProviderModal({ open, onClose, row, onTestProvider }) {
  const [form, setForm] = useState({
    // LLM / Image / Video
    prompt: '',
    system: '',
    aspect_ratio: '',
    duration_s: '',
    // TTS
    text: '',
    voice_tone: '',
    language: '',
    // STT
    audio_b64: '',
    audio_mime: '',
    audio_filename: '',
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [validationError, setValidationError] = useState(null);

  const modality = row?.modality;

  const resetAll = () => {
    setForm({
      prompt: '', system: '', aspect_ratio: '', duration_s: '',
      text: '', voice_tone: '', language: '',
      audio_b64: '', audio_mime: '', audio_filename: '',
    });
    setResult(null);
    setValidationError(null);
  };

  const handleClose = () => {
    if (running) return;
    resetAll();
    onClose?.();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setValidationError(null);

    const payload = buildTestPayload(modality, form);
    if (payload.error) { setValidationError(payload.error); return; }

    setRunning(true);
    setResult(null);
    try {
      const response = await onTestProvider?.(modality, payload.body);
      setResult(response);
    } catch (err) {
      // Errores no-Provider (red caída, 5xx del wrapper) llegan acá.
      setResult({
        ok: false,
        modality,
        provider: row?.provider,
        model: row?.model,
        error: err?.message || 'Network error',
        error_class: 'NetworkError',
        elapsed_ms: 0,
      });
    } finally {
      setRunning(false);
    }
  };

  const handleAudioFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const buf = await file.arrayBuffer();
    // btoa(String.fromCharCode(...bytes)) explota para audios grandes
    // (límite ~64KB en algunos browsers). Iteramos manualmente en chunks.
    const bytes = new Uint8Array(buf);
    let binary = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    const b64 = btoa(binary);
    setForm((p) => ({
      ...p,
      audio_b64: b64,
      audio_mime: file.type || 'audio/mpeg',
      audio_filename: file.name,
    }));
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={modality ? `Probar ${modalityLabel(modality)}` : ''}
      description={
        row
          ? `${providerLabel(row.provider)} · ${row.model || '—'}`
          : 'Smoke test del provider configurado'
      }
      size="md"
      footer={
        <>
          <Button type="button" variant="ghost" onClick={handleClose} disabled={running}>
            Cerrar
          </Button>
          <Button
            type="submit"
            form="ai-providers-test"
            variant="primary"
            loading={running}
            disabled={running}
          >
            Ejecutar
          </Button>
        </>
      }
    >
      <form
        id="ai-providers-test"
        className={styles.form}
        onSubmit={handleSubmit}
        autoComplete="off"
      >
        <TestInputs modality={modality} form={form} setForm={setForm} onAudioFile={handleAudioFile} />

        {validationError ? (
          <AlertBanner tone="warn">{validationError}</AlertBanner>
        ) : null}

        {result ? <TestResult result={result} /> : null}
      </form>
    </Modal>
  );
}


/* ─── inputs por modalidad ─────────────────────────────────────────────── */

function TestInputs({ modality, form, setForm, onAudioFile }) {
  if (modality === 'llm') {
    return (
      <>
        <FormField label="System (opcional)" hint="Instrucción inicial al modelo (ej. 'You are a helpful assistant')">
          <textarea
            rows={2}
            value={form.system}
            onChange={(e) => setForm((p) => ({ ...p, system: e.target.value }))}
            placeholder="You are a helpful assistant."
          />
        </FormField>
        <FormField label="Prompt" hint="Mensaje del usuario que envías al modelo.">
          <textarea
            rows={4}
            value={form.prompt}
            onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
            placeholder="Dame una idea para un post sobre café."
            required
          />
        </FormField>
      </>
    );
  }
  if (modality === 'image') {
    return (
      <>
        <FormField label="Prompt" hint="Describe la imagen que quieres generar.">
          <textarea
            rows={3}
            value={form.prompt}
            onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
            placeholder="A futuristic city skyline at sunset."
            required
          />
        </FormField>
        <FormField label="Aspect ratio" hint="1:1, 16:9, 9:16, 4:3, 3:4, 2:1, 1:2 — o 'auto'.">
          <input
            type="text"
            value={form.aspect_ratio}
            onChange={(e) => setForm((p) => ({ ...p, aspect_ratio: e.target.value }))}
            placeholder="1:1"
            list="img-aspect-ratios"
          />
          <datalist id="img-aspect-ratios">
            {['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', 'auto'].map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>
        </FormField>
      </>
    );
  }
  if (modality === 'video') {
    return (
      <>
        <FormField label="Prompt" hint="Describe el video que quieres generar.">
          <textarea
            rows={3}
            value={form.prompt}
            onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
            placeholder="Slow drone shot of waves crashing at sunset."
            required
          />
        </FormField>
        <FormField label="Duración (segundos)" hint="Entre 1 y 15s. Default: 5s.">
          <input
            type="number"
            min="1"
            max="15"
            step="1"
            value={form.duration_s}
            onChange={(e) => setForm((p) => ({ ...p, duration_s: e.target.value }))}
            placeholder="5"
          />
        </FormField>
        <FormField label="Aspect ratio" hint="16:9 (default), 9:16, 1:1, 4:3, 3:4.">
          <input
            type="text"
            value={form.aspect_ratio}
            onChange={(e) => setForm((p) => ({ ...p, aspect_ratio: e.target.value }))}
            placeholder="16:9"
            list="vid-aspect-ratios"
          />
          <datalist id="vid-aspect-ratios">
            {['16:9', '9:16', '1:1', '4:3', '3:4'].map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>
        </FormField>
        <AlertBanner tone="info">
          La generación de video toma 1–10 min según duración y resolución.
          La ventana puede quedar abierta hasta que termine.
        </AlertBanner>
      </>
    );
  }
  if (modality === 'tts') {
    return (
      <>
        <FormField label="Texto" hint="Lo que el modelo debe leer en voz alta.">
          <textarea
            rows={3}
            value={form.text}
            onChange={(e) => setForm((p) => ({ ...p, text: e.target.value }))}
            placeholder="Hola, soy un asistente virtual."
            required
          />
        </FormField>
        <FormField label="Idioma" hint="Código ISO de idioma (es, en, pt…). Default: es.">
          <input
            type="text"
            value={form.language}
            onChange={(e) => setForm((p) => ({ ...p, language: e.target.value }))}
            placeholder="es"
            list="tts-langs"
            maxLength={8}
          />
          <datalist id="tts-langs">
            {['es', 'en', 'pt', 'fr', 'it', 'de'].map((l) => (
              <option key={l} value={l} />
            ))}
          </datalist>
        </FormField>
        <FormField label="Tono de voz (opcional)" hint="Ej. 'cálida', 'profesional', 'energética'.">
          <input
            type="text"
            value={form.voice_tone}
            onChange={(e) => setForm((p) => ({ ...p, voice_tone: e.target.value }))}
            placeholder="cálida"
          />
        </FormField>
      </>
    );
  }
  if (modality === 'stt') {
    return (
      <>
        <FormField label="Archivo de audio" hint="WAV / MP3 / WebM. El archivo se envía como base64 al backend.">
          <input
            type="file"
            accept="audio/*"
            onChange={onAudioFile}
          />
          {form.audio_filename ? (
            <p className={styles.hint}>
              Cargado: <strong>{form.audio_filename}</strong> (
              {Math.round((form.audio_b64.length * 3) / 4 / 1024)} KB,{' '}
              {form.audio_mime})
            </p>
          ) : null}
        </FormField>
        <FormField label="Idioma esperado (opcional)" hint="Sugerencia al modelo. Si lo dejas vacío, autodetecta.">
          <input
            type="text"
            value={form.language}
            onChange={(e) => setForm((p) => ({ ...p, language: e.target.value }))}
            placeholder="es"
            list="stt-langs"
            maxLength={8}
          />
          <datalist id="stt-langs">
            {['es', 'en', 'pt', 'fr'].map((l) => (
              <option key={l} value={l} />
            ))}
          </datalist>
        </FormField>
      </>
    );
  }
  return null;
}


/* ─── render del resultado ─────────────────────────────────────────────── */

function TestResult({ result }) {
  if (!result.ok) {
    return (
      <div className={styles.resultBox} data-testid="test-result-error">
        <header className={styles.resultHeader}>
          <StatusBadge tone="danger">FAIL</StatusBadge>
          <span className={styles.muted}>
            {result.elapsed_ms ? `${Math.round(result.elapsed_ms)}ms` : '—'}
          </span>
        </header>
        <p className={styles.resultErrorClass}>{result.error_class || 'Error'}</p>
        <pre className={styles.resultErrorBody}>{result.error}</pre>
      </div>
    );
  }
  const out = result.output || {};
  return (
    <div className={styles.resultBox} data-testid="test-result-ok">
      <header className={styles.resultHeader}>
        <StatusBadge tone="success">OK</StatusBadge>
        <span className={styles.muted}>{Math.round(result.elapsed_ms)}ms</span>
      </header>
      {out.kind === 'text' ? (
        <>
          <pre className={styles.resultText}>{out.text}</pre>
          {out.tokens_used != null ? (
            <p className={styles.muted}>
              Tokens: {out.tokens_used} · Finish: {out.finish_reason || '—'}
            </p>
          ) : null}
        </>
      ) : null}
      {out.kind === 'image' ? (
        <>
          <img
            className={styles.resultImage}
            src={`data:${out.mime};base64,${out.image_b64}`}
            alt="Resultado del modelo"
          />
          <p className={styles.muted}>{out.width}×{out.height} · {out.mime}</p>
        </>
      ) : null}
      {out.kind === 'video' ? (
        <>
          {/* controls habilitados — el operador valida visualmente que el
              video se generó. `data:` URL es válido para video src. */}
          <video
            className={styles.resultVideo}
            controls
            src={`data:${out.mime};base64,${out.video_b64}`}
          />
          <p className={styles.muted}>
            {out.duration_s}s · {out.width}×{out.height} · {out.mime}
          </p>
        </>
      ) : null}
      {out.kind === 'audio' ? (
        <>
          <audio
            controls
            src={`data:${out.mime};base64,${out.audio_b64}`}
          />
          <p className={styles.muted}>
            {out.duration_s}s · {out.sample_rate}Hz · {out.mime}
          </p>
        </>
      ) : null}
      {out.kind === 'transcript' ? (
        <>
          <pre className={styles.resultText}>{out.text}</pre>
          <p className={styles.muted}>
            Idioma: {out.language || '—'} · Confianza:{' '}
            {out.confidence != null ? out.confidence.toFixed(2) : '—'}
          </p>
        </>
      ) : null}
    </div>
  );
}


/* ─── construcción del payload por modalidad ─────────────────────────── */

export function buildTestPayload(modality, form) {
  if (modality === 'llm') {
    if (!form.prompt?.trim()) return { error: 'Escribe un prompt para probar el modelo.' };
    return { body: { prompt: form.prompt, system: form.system || null } };
  }
  if (modality === 'image') {
    if (!form.prompt?.trim()) return { error: 'Escribe un prompt para probar la generación.' };
    return {
      body: {
        prompt: form.prompt,
        aspect_ratio: form.aspect_ratio || null,
      },
    };
  }
  if (modality === 'video') {
    if (!form.prompt?.trim()) return { error: 'Escribe un prompt para probar la generación.' };
    const dur = form.duration_s ? Number(form.duration_s) : null;
    if (dur != null && (Number.isNaN(dur) || dur < 1 || dur > 15)) {
      return { error: 'La duración debe estar entre 1 y 15 segundos.' };
    }
    return {
      body: {
        prompt: form.prompt,
        aspect_ratio: form.aspect_ratio || null,
        duration_s: dur,
      },
    };
  }
  if (modality === 'tts') {
    if (!form.text?.trim()) return { error: 'Escribe el texto que quieres convertir a voz.' };
    return {
      body: {
        text: form.text,
        language: form.language || null,
        voice_tone: form.voice_tone || null,
      },
    };
  }
  if (modality === 'stt') {
    if (!form.audio_b64) return { error: 'Carga un archivo de audio antes de ejecutar.' };
    return {
      body: {
        audio_b64: form.audio_b64,
        audio_mime: form.audio_mime || null,
        language: form.language || null,
      },
    };
  }
  return { error: `Modalidad no soportada: ${modality}` };
}
