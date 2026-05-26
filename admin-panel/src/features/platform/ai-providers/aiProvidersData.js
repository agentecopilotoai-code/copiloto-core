/**
 * Helpers puros para la config de proveedores IA transversales.
 *
 * Los providers IA (LLM/Image/Video/TTS/STT) son un recurso de plataforma
 * usado por cualquier módulo opt-in que se instale sobre el core.
 * Este archivo NO depende de ningún módulo en particular.
 */

export const MODALITIES = [
  { value: 'llm', label: 'LLM' },
  { value: 'image', label: 'Image' },
  { value: 'video', label: 'Video' },
  { value: 'tts', label: 'TTS' },
  { value: 'stt', label: 'STT' },
];

export const PROVIDERS_BY_MODALITY = {
  llm: ['grok', 'anthropic', 'openai', 'ollama'],
  image: ['grok', 'openai', 'local_sdxl'],
  video: ['grok'],
  tts: ['grok', 'openai', 'elevenlabs'],
  stt: ['grok', 'openai', 'local_whisper'],
};

/**
 * Sugerencias de modelo por (provider, modality). El input del modal usa
 * <datalist> para mostrarlas, pero el operador puede tipear un modelo libre
 * (modelos nuevos no listados aún, builds privados, etc.). Fuente para
 * Grok: `docs/xGrok/{Generate Text,Imagine Overview,Video Generation,Voice
 * Agent API}` capturados 2026-05-20. Para otros providers: catálogo público
 * a la fecha; el operador siempre puede sobreescribir manualmente.
 */
export const MODEL_SUGGESTIONS_BY_PROVIDER_MODALITY = {
  grok: {
    llm: [
      'grok-4.3',
      'grok-4.20-multi-agent-0309',
      'grok-4.20-0309-reasoning',
      'grok-4.20-0309-non-reasoning',
      'grok-build-0.1',
    ],
    image: [
      'grok-imagine-image-quality',
      'grok-imagine-image',
    ],
    video: [
      'grok-imagine-video',
    ],
    tts: [
      'grok-voice-latest',
      'grok-voice-think-fast-1.0',
    ],
    stt: [
      'grok-voice-latest',
      'grok-voice-think-fast-1.0',
    ],
  },
  anthropic: {
    llm: [
      'claude-opus-4-7',
      'claude-sonnet-4-6',
      'claude-haiku-4-5-20251001',
    ],
  },
  openai: {
    llm: ['gpt-5', 'gpt-4.1', 'gpt-4o', 'gpt-4o-mini'],
    image: ['dall-e-3', 'dall-e-2'],
    tts: ['tts-1-hd', 'tts-1'],
    stt: ['whisper-1'],
  },
  elevenlabs: {
    tts: [
      'eleven_multilingual_v2',
      'eleven_turbo_v2_5',
      'eleven_flash_v2_5',
    ],
  },
  ollama: {
    llm: ['llama3.3', 'llama3.2', 'qwen2.5', 'mistral'],
  },
  local_sdxl: {
    image: ['sdxl-base-1.0', 'sdxl-turbo'],
  },
  local_whisper: {
    stt: ['whisper-large-v3', 'whisper-medium', 'whisper-small'],
  },
};

/**
 * Sugerencias para un par (provider, modality). Devuelve [] cuando no hay
 * combinación conocida — el input sigue siendo escribible libre.
 */
export function modelSuggestionsFor(provider, modality) {
  if (!provider || provider === 'unset') return [];
  return MODEL_SUGGESTIONS_BY_PROVIDER_MODALITY[provider]?.[modality] || [];
}


/**
 * ¿La fila tiene provider + modelo + key configurados? El botón "Probar"
 * solo se habilita cuando esto es true (no tiene sentido testear una
 * modalidad sin proveedor o sin key). Los 3 son necesarios:
 *   - `provider !== 'unset'` — está seleccionado un vendor
 *   - `model` — hay un modelo elegido para mandar al endpoint
 *   - `hint` — hay una key rotada (el backend la resuelve por env var)
 */
export function isModalityConfigured(row) {
  if (!row) return false;
  return (
    row.provider !== 'unset'
    && Boolean(row.model)
    && Boolean(row.hint)
  );
}

const PROVIDER_LABELS = {
  grok: 'xAI Grok',
  anthropic: 'Anthropic Claude',
  openai: 'OpenAI',
  elevenlabs: 'ElevenLabs',
  ollama: 'Ollama (local)',
  local_sdxl: 'SDXL (local)',
  local_whisper: 'Whisper (local)',
  unset: '— sin configurar',
};


export function modalityLabel(value) {
  return MODALITIES.find((m) => m.value === value)?.label || value || '—';
}


export function providerLabel(value) {
  return PROVIDER_LABELS[value] || value || '—';
}


/**
 * Valida que el modelo sea coherente con el provider seleccionado.
 * - Grok: solo `grok-*`.
 * - Anthropic: solo `claude-*`.
 * - OpenAI: cualquier modelo (gpt-*, dall-e-*, tts-1, whisper-1).
 * - ElevenLabs: cualquier voice/model id de Eleven (no validamos, opaco).
 * - Locales: no validamos.
 */
export function validateModelByProvider(provider, model) {
  if (!model) return { valid: true };  // model opcional
  const m = String(model).toLowerCase();
  if (provider === 'grok' && !m.startsWith('grok-')) {
    return { valid: false, error: 'Modelo Grok debe empezar con grok-' };
  }
  if (provider === 'anthropic' && !m.startsWith('claude-')) {
    return { valid: false, error: 'Modelo Anthropic debe empezar con claude-' };
  }
  return { valid: true };
}


export function buildPatchPayload(form) {
  const payload = {
    provider: form.provider,
    model: form.model || null,
    params: form.params || {},
  };
  // Mutación del secret: dos modos, mutuamente excluyentes.
  //
  //   - `form.reuse_from_modality` — la UI marcó el checkbox "usar la misma
  //     key que <otra modalidad>". El backend resuelve el `secret_ref` por
  //     el lado del servidor; el frontend NUNCA ve el `secret_ref` opaco ni
  //     la key en claro.
  //
  //   - `form.api_key` — el operador tipeó una key nueva. La mandamos como
  //     `secret_value` (nombre canónico del schema pydantic). BUGFIX previo:
  //     antes enviábamos `api_key`, pydantic lo ignoraba y la rotación nunca
  //     llegaba al storage.
  //
  // Si vienen ambos, reuse gana — el operador explícitamente seleccionó la
  // opción "reusar"; la key tipeada se descarta sin enviarla. Esto evita
  // que un input residual con texto viejo dispare una rotación accidental.
  if (form.reuse_from_modality) {
    payload.reuse_from_modality = form.reuse_from_modality;
  } else if (form.api_key) {
    payload.secret_value = form.api_key;
  }
  return payload;
}
