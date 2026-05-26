import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TestProviderModal, buildTestPayload } from './TestProviderModal.jsx';

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
    expect(buildTestPayload('video', { prompt: '' }).error).toMatch(/prompt/i);
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

describe('<TestProviderModal/> — render', () => {
  beforeEach(() => {
    // jsdom Modal mounts via portal; clean any leftover.
    document.body.innerHTML = '';
  });

  it('LLM modality: prompt + system inputs, ejecuta y muestra resultado text', async () => {
    const onTestProvider = vi.fn().mockResolvedValue({
      ok: true,
      modality: 'llm',
      provider: 'grok',
      model: 'grok-4.3',
      elapsed_ms: 1234,
      output: { kind: 'text', text: 'Hola mundo', tokens_used: 42, finish_reason: 'stop' },
    });
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'llm', provider: 'grok', model: 'grok-4.3' }}
        onTestProvider={onTestProvider}
      />,
    );
    const prompt = screen.getByPlaceholderText(/idea para un post/);
    await userEvent.type(prompt, 'Hola');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      expect(screen.getByTestId('test-result-ok')).toBeInTheDocument();
    });
    expect(screen.getByText('Hola mundo')).toBeInTheDocument();
    expect(screen.getByText(/Tokens: 42/)).toBeInTheDocument();
  });

  it('LLM: prompt vacío dispara validation banner', async () => {
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'llm', provider: 'grok' }}
        onTestProvider={vi.fn()}
      />,
    );
    // No-op submit (prompt vacío); pero el textarea es `required` HTML, así que
    // forzamos el handler vía submit() directo.
    const form = document.getElementById('ai-providers-test');
    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    await waitFor(() => {
      expect(screen.getByText(/Escribe un prompt/i)).toBeInTheDocument();
    });
  });

  it('Image modality: pinta el resultado image', async () => {
    const onTestProvider = vi.fn().mockResolvedValue({
      ok: true, modality: 'image', provider: 'grok', elapsed_ms: 500,
      output: { kind: 'image', mime: 'image/png', image_b64: 'AAA', width: 1024, height: 1024 },
    });
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'image', provider: 'grok', model: 'm1' }}
        onTestProvider={onTestProvider}
      />,
    );
    await userEvent.type(screen.getByPlaceholderText(/futuristic city/), 'A city');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      expect(screen.getByRole('img', { name: /Resultado/i })).toBeInTheDocument();
    });
    expect(screen.getByText('1024×1024 · image/png')).toBeInTheDocument();
  });

  it('Video modality: muestra el video con URL', async () => {
    const onTestProvider = vi.fn().mockResolvedValue({
      ok: true, modality: 'video', provider: 'grok', elapsed_ms: 9000,
      output: {
        kind: 'video', video_url: 'https://cdn/x.mp4', mime: 'video/mp4',
        duration_s: 5, width: 1920, height: 1080,
      },
    });
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'video', provider: 'grok' }}
        onTestProvider={onTestProvider}
      />,
    );
    await userEvent.type(screen.getByPlaceholderText(/Slow drone shot/), 'A wave');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      const video = document.querySelector('video');
      expect(video).not.toBeNull();
      expect(video.getAttribute('src')).toBe('https://cdn/x.mp4');
    });
  });

  it('TTS modality: pinta audio', async () => {
    const onTestProvider = vi.fn().mockResolvedValue({
      ok: true, modality: 'tts', provider: 'grok', elapsed_ms: 800,
      output: { kind: 'audio', mime: 'audio/mp3', audio_b64: 'AAA', duration_s: 2, sample_rate: 44100 },
    });
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'tts', provider: 'grok' }}
        onTestProvider={onTestProvider}
      />,
    );
    await userEvent.type(screen.getByPlaceholderText(/asistente virtual/), 'Hola');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      const audio = document.querySelector('audio');
      expect(audio).not.toBeNull();
    });
    expect(screen.getByText(/44100Hz/)).toBeInTheDocument();
  });

  it('STT modality: requiere file upload, pinta transcript', async () => {
    const onTestProvider = vi.fn().mockResolvedValue({
      ok: true, modality: 'stt', provider: 'grok', elapsed_ms: 600,
      output: { kind: 'transcript', text: 'Buenos días', language: 'es', confidence: 0.92 },
    });
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'stt', provider: 'grok' }}
        onTestProvider={onTestProvider}
      />,
    );
    // Cargamos un file mock. arrayBuffer() puede no estar en jsdom <22 —
    // shim defensivo.
    const file = new File(['audio-bytes-here'], 'voice.wav', { type: 'audio/wav' });
    if (typeof file.arrayBuffer !== 'function') {
      file.arrayBuffer = async () => new Uint8Array([1, 2, 3]).buffer;
    }
    const input = document.querySelector('input[type="file"]');
    await userEvent.upload(input, file);
    await waitFor(() => {
      expect(screen.getByText(/Cargado:/)).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      expect(screen.getByText('Buenos días')).toBeInTheDocument();
    });
    expect(screen.getByText(/Idioma: es/)).toBeInTheDocument();
  });

  it('result error path con StatusBadge FAIL', async () => {
    const onTestProvider = vi.fn().mockResolvedValue({
      ok: false,
      modality: 'llm', provider: 'grok', elapsed_ms: 200,
      error: 'rate limited',
      error_class: 'ProviderRateLimited',
    });
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'llm', provider: 'grok' }}
        onTestProvider={onTestProvider}
      />,
    );
    await userEvent.type(screen.getByPlaceholderText(/idea para un post/), 'hi');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      expect(screen.getByTestId('test-result-error')).toBeInTheDocument();
    });
    expect(screen.getByText('ProviderRateLimited')).toBeInTheDocument();
    expect(screen.getByText('rate limited')).toBeInTheDocument();
  });

  it('exception del onTestProvider se transforma en NetworkError result', async () => {
    const onTestProvider = vi.fn().mockRejectedValue(new Error('boom'));
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'llm', provider: 'grok' }}
        onTestProvider={onTestProvider}
      />,
    );
    await userEvent.type(screen.getByPlaceholderText(/idea para un post/), 'hi');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    await waitFor(() => {
      expect(screen.getByText('NetworkError')).toBeInTheDocument();
    });
  });

  it('validation error pinta cuando buildTestPayload retorna error', async () => {
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'stt', provider: 'grok' }}
        onTestProvider={vi.fn()}
      />,
    );
    // STT sin file → validation error.
    const form = document.getElementById('ai-providers-test');
    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    await waitFor(() => {
      expect(screen.getByText(/Carga un archivo/i)).toBeInTheDocument();
    });
  });

  it('handleClose es no-op cuando running=true', async () => {
    let resolveTest;
    const onTestProvider = vi.fn().mockReturnValue(
      new Promise((resolve) => { resolveTest = resolve; }),
    );
    const onClose = vi.fn();
    render(
      <TestProviderModal
        open
        onClose={onClose}
        row={{ modality: 'llm', provider: 'grok' }}
        onTestProvider={onTestProvider}
      />,
    );
    await userEvent.type(screen.getByPlaceholderText(/idea para un post/), 'hi');
    await userEvent.click(screen.getByRole('button', { name: 'Ejecutar' }));
    // Mientras running está true, Cerrar es no-op.
    const closeBtns = screen.getAllByRole('button', { name: 'Cerrar' });
    // Click el del footer (last); el del header tiene aria-label='Cerrar' del Modal.
    await userEvent.click(closeBtns.at(-1));
    expect(onClose).not.toHaveBeenCalled();
    // Resolvemos para limpiar el state.
    resolveTest({ ok: true, modality: 'llm', provider: 'grok', elapsed_ms: 0, output: { kind: 'text', text: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('test-result-ok')).toBeInTheDocument();
    });
  });

  it('handleClose limpia state cuando no está running', async () => {
    const onClose = vi.fn();
    render(
      <TestProviderModal
        open
        onClose={onClose}
        row={{ modality: 'llm', provider: 'grok' }}
        onTestProvider={vi.fn()}
      />,
    );
    const closeBtns = screen.getAllByRole('button', { name: 'Cerrar' });
    await userEvent.click(closeBtns.at(-1));
    expect(onClose).toHaveBeenCalled();
  });

  it('row null usa el subtítulo genérico', () => {
    render(
      <TestProviderModal open onClose={() => {}} row={null} onTestProvider={vi.fn()} />,
    );
    expect(screen.getByText(/Smoke test del provider/)).toBeInTheDocument();
  });

  it('modalidad desconocida no pinta ningún input (TestInputs → null)', () => {
    render(
      <TestProviderModal
        open
        onClose={() => {}}
        row={{ modality: 'unknown', provider: 'x' }}
        onTestProvider={vi.fn()}
      />,
    );
    // No hay <textarea> ni input file.
    expect(document.querySelector('textarea')).toBeNull();
  });
});
