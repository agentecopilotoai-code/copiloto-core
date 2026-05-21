import { describe, it, expect } from 'vitest';

import {
  buildPatchPayload,
  isModalityConfigured,
  modalityLabel,
  modelSuggestionsFor,
  providerLabel,
  validateModelByProvider,
} from './aiProvidersData.js';


describe('aiProvidersData (proveedores IA transversales)', () => {
  it('modalityLabel mapea modalidades', () => {
    expect(modalityLabel('llm')).toBe('LLM');
    expect(modalityLabel('image')).toBe('Image');
    expect(modalityLabel('unknown')).toBe('unknown');
  });

  it('providerLabel mapea providers a labels human-readable', () => {
    expect(providerLabel('grok')).toBe('xAI Grok');
    expect(providerLabel('anthropic')).toBe('Anthropic Claude');
    expect(providerLabel('elevenlabs')).toBe('ElevenLabs');
    expect(providerLabel('unset')).toBe('— sin configurar');
  });

  it('validateModelByProvider rechaza modelos incoherentes', () => {
    expect(validateModelByProvider('grok', 'grok-4.3').valid).toBe(true);
    expect(validateModelByProvider('grok', 'claude-x').valid).toBe(false);
    expect(validateModelByProvider('anthropic', 'claude-sonnet-4-6').valid).toBe(true);
    expect(validateModelByProvider('anthropic', 'gpt-4').valid).toBe(false);
    expect(validateModelByProvider('openai', 'gpt-4o-mini').valid).toBe(true);  // libre
    expect(validateModelByProvider('grok', '').valid).toBe(true);  // model vacío permitido
  });

  it('buildPatchPayload incluye secret_value SOLO si fue provista', () => {
    // Sin api_key en el form → no se envía secret_value (no rota la key).
    const noKey = buildPatchPayload({ provider: 'grok', model: 'grok-4.3' });
    expect(noKey.secret_value).toBeUndefined();
    expect(noKey.api_key).toBeUndefined();

    // Con api_key → se mapea a secret_value (la key oficial del backend).
    const withKey = buildPatchPayload({
      provider: 'grok', model: 'grok-4.3', api_key: 'xai-key-123',
    });
    expect(withKey.secret_value).toBe('xai-key-123');
    // BUGFIX: nunca enviamos el nombre legacy `api_key` al backend porque
    // pydantic lo ignora silenciosamente.
    expect(withKey.api_key).toBeUndefined();
  });

  it('buildPatchPayload con reuse_from_modality NO envía secret_value', () => {
    // Caso típico: el operador marcó "reusar key de image"; el input de
    // API Key queda vacío (la UI lo deshabilita).
    const reusing = buildPatchPayload({
      provider: 'grok', model: 'grok-4.3',
      reuse_from_modality: 'image',
    });
    expect(reusing.reuse_from_modality).toBe('image');
    expect(reusing.secret_value).toBeUndefined();
    expect(reusing.api_key).toBeUndefined();
  });

  it('buildPatchPayload: reuse gana sobre api_key si ambos vienen', () => {
    // Defensa: si por bug de UI quedó una key residual en el input, NO
    // queremos rotar accidentalmente. El reuse explícito tiene prioridad.
    const both = buildPatchPayload({
      provider: 'grok', model: 'grok-4.3',
      reuse_from_modality: 'image',
      api_key: 'xai-stale-key',
    });
    expect(both.reuse_from_modality).toBe('image');
    expect(both.secret_value).toBeUndefined();
  });

  it('isModalityConfigured requiere provider + model + hint los tres', () => {
    // Caso típico: fila configurada → true.
    expect(isModalityConfigured({
      provider: 'grok', model: 'grok-4.3', hint: 'AB12',
    })).toBe(true);
    // Faltantes individuales → false.
    expect(isModalityConfigured({
      provider: 'unset', model: 'grok-4.3', hint: 'AB12',
    })).toBe(false);
    expect(isModalityConfigured({
      provider: 'grok', model: null, hint: 'AB12',
    })).toBe(false);
    expect(isModalityConfigured({
      provider: 'grok', model: 'grok-4.3', hint: null,
    })).toBe(false);
    expect(isModalityConfigured(null)).toBe(false);
    expect(isModalityConfigured(undefined)).toBe(false);
  });

  it('modelSuggestionsFor devuelve los modelos canónicos por (provider, modality)', () => {
    // Grok según docs/xGrok/* (commit 2026-05-20).
    expect(modelSuggestionsFor('grok', 'llm')).toContain('grok-4.3');
    expect(modelSuggestionsFor('grok', 'image')).toContain('grok-imagine-image-quality');
    expect(modelSuggestionsFor('grok', 'video')).toContain('grok-imagine-video');
    expect(modelSuggestionsFor('grok', 'tts')).toContain('grok-voice-latest');
    expect(modelSuggestionsFor('grok', 'stt')).toContain('grok-voice-latest');
    // Otros providers también tienen sugerencias mínimas.
    expect(modelSuggestionsFor('anthropic', 'llm').length).toBeGreaterThan(0);
    expect(modelSuggestionsFor('openai', 'image')).toContain('dall-e-3');
    expect(modelSuggestionsFor('elevenlabs', 'tts').length).toBeGreaterThan(0);
    // (provider, modality) no soportada → []. La UI cae a input freeform.
    expect(modelSuggestionsFor('grok', 'noexiste')).toEqual([]);
    expect(modelSuggestionsFor('unset', 'llm')).toEqual([]);
    expect(modelSuggestionsFor(null, 'llm')).toEqual([]);
  });
});
