import { describe, it, expect } from 'vitest';

import { buildTestPayload } from './TestProviderModal.jsx';

describe('buildTestPayload', () => {
  it('llm: prompt requerido', () => {
    expect(buildTestPayload('llm', { prompt: '' }).error).toMatch(/prompt/i);
    const ok = buildTestPayload('llm', { prompt: 'Hola', system: 'Be brief' });
    expect(ok.error).toBeUndefined();
    expect(ok.body).toEqual({ prompt: 'Hola', system: 'Be brief' });
  });

  it('llm: system queda null si no se provee', () => {
    const ok = buildTestPayload('llm', { prompt: 'Hola' });
    expect(ok.body.system).toBeNull();
  });

  it('image: aspect_ratio opcional, prompt requerido', () => {
    expect(buildTestPayload('image', { prompt: '' }).error).toMatch(/prompt/i);
    const r = buildTestPayload('image', { prompt: 'A cat', aspect_ratio: '16:9' });
    expect(r.body.aspect_ratio).toBe('16:9');
  });

  it('video: duración fuera de 1..15 rechazada', () => {
    expect(buildTestPayload('video', { prompt: 'A', duration_s: '0' }).error).toMatch(/duración/i);
    expect(buildTestPayload('video', { prompt: 'A', duration_s: '20' }).error).toMatch(/duración/i);
    expect(buildTestPayload('video', { prompt: 'A', duration_s: '5' }).body.duration_s).toBe(5);
    expect(buildTestPayload('video', { prompt: 'A' }).body.duration_s).toBeNull();
  });

  it('tts: text requerido, voice_tone y language opcionales', () => {
    expect(buildTestPayload('tts', { text: '' }).error).toMatch(/texto/i);
    const r = buildTestPayload('tts', {
      text: 'Hola', language: 'es', voice_tone: 'cálida',
    });
    expect(r.body).toEqual({ text: 'Hola', language: 'es', voice_tone: 'cálida' });
  });

  it('stt: requiere audio_b64; idioma opcional', () => {
    expect(buildTestPayload('stt', { audio_b64: '' }).error).toMatch(/audio/i);
    const r = buildTestPayload('stt', {
      audio_b64: 'AAAA', audio_mime: 'audio/wav', language: 'en',
    });
    expect(r.body).toEqual({ audio_b64: 'AAAA', audio_mime: 'audio/wav', language: 'en' });
  });

  it('rechaza modalidad desconocida', () => {
    expect(buildTestPayload('xxx', {}).error).toMatch(/no soportada/i);
  });
});
