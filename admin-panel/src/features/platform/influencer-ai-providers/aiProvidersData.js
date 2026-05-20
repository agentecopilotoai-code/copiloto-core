/**
 * UI-INFLU-015 — Helpers puros para la config de proveedores IA del módulo.
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
  // api_key solo se incluye si el operador la cambió (write-only).
  if (form.api_key) {
    payload.api_key = form.api_key;
  }
  return payload;
}
