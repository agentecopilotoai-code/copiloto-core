import { describe, it, expect } from 'vitest';

import {
  buildPatchPayload,
  modalityLabel,
  providerLabel,
  validateModelByProvider,
} from './aiProvidersData.js';


describe('aiProvidersData (UI-INFLU-015)', () => {
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

  it('buildPatchPayload incluye api_key SOLO si fue provista', () => {
    expect(buildPatchPayload({
      provider: 'grok', model: 'grok-4.3',
    }).api_key).toBeUndefined();
    expect(buildPatchPayload({
      provider: 'grok', model: 'grok-4.3', api_key: 'xai-key-123',
    }).api_key).toBe('xai-key-123');
  });
});
