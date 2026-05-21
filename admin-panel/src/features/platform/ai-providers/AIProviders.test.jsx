import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AIProviders } from './AIProviders.jsx';


const ROWS = [
  { modality: 'llm', provider: 'grok', model: 'grok-4.3', hint: 'b12c', rotated_at: '2026-05-10 14:30' },
  { modality: 'image', provider: 'grok', model: 'grok-imagine-image', hint: 'xyz9', rotated_at: '2026-05-10 14:32' },
];


describe('<AIProviders/> — proveedores IA transversales (platform_owner only)', () => {
  it('render tabla con las 5 modalidades', () => {
    render(<AIProviders rows={ROWS} />);
    expect(screen.getByText('LLM')).toBeInTheDocument();
    expect(screen.getByText('Image')).toBeInTheDocument();
    expect(screen.getByText('Video')).toBeInTheDocument();
    expect(screen.getByText('TTS')).toBeInTheDocument();
    expect(screen.getByText('STT')).toBeInTheDocument();
  });

  it('Editar abre drawer prefill con provider+model actuales y NO con api_key', async () => {
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} />);
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    await user.click(editButtons[0]);  // LLM row
    expect(screen.getByLabelText('Provider')).toHaveValue('grok');
    expect(screen.getByPlaceholderText(/grok-4.3/i)).toBeInTheDocument();
    // El input de API Key debe estar VACÍO (placeholder visible).
    const apiKeyInput = screen.getByPlaceholderText(/Se sobrescribirá la actual/i);
    expect(apiKeyInput).toHaveValue('');
  });

  it('Guardar dispara onSave con payload correcto (mapea api_key → secret_value)', async () => {
    const onSave = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onSave={onSave} />);
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    const apiKeyInput = screen.getByPlaceholderText(/Se sobrescribirá la actual/i);
    await user.type(apiKeyInput, 'new-key-xyz');
    await user.click(screen.getByRole('button', { name: 'Guardar' }));
    // BUGFIX — el backend espera `secret_value`, no `api_key`. La UI sigue
    // mostrando "API Key" al operador, pero el wire format usa la key
    // oficial del schema pydantic.
    expect(onSave).toHaveBeenCalledWith('llm', expect.objectContaining({ secret_value: 'new-key-xyz' }));
    expect(onSave.mock.calls[0][1].api_key).toBeUndefined();
  });

  it('Guardar sin api_key no envía secret_value en el payload', async () => {
    const onSave = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onSave={onSave} />);
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    await user.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(onSave).toHaveBeenCalled();
    expect(onSave.mock.calls[0][1].secret_value).toBeUndefined();
    expect(onSave.mock.calls[0][1].api_key).toBeUndefined();
  });

  it('"Probar" deshabilitado si la modalidad no está configurada', () => {
    // ROW3..ROW5 (video/tts/stt) NO están en ROWS → fallback con provider=unset.
    render(<AIProviders rows={ROWS} />);
    const probarButtons = screen.getAllByRole('button', { name: 'Probar' });
    // 5 modalidades, 5 botones — los primeros 2 (llm/image) están configurados,
    // los otros 3 (video/tts/stt) no.
    expect(probarButtons).toHaveLength(5);
    expect(probarButtons[0]).toBeEnabled();   // llm
    expect(probarButtons[1]).toBeEnabled();   // image
    expect(probarButtons[2]).toBeDisabled();  // video
    expect(probarButtons[3]).toBeDisabled();  // tts
    expect(probarButtons[4]).toBeDisabled();  // stt
  });

  it('"Probar" abre el modal de prueba y dispara onTestProvider con el prompt', async () => {
    const onTest = vi.fn().mockResolvedValue({
      ok: true,
      modality: 'llm',
      provider: 'grok',
      model: 'grok-4.3',
      elapsed_ms: 234,
      output: { kind: 'text', text: 'Hola desde Grok', tokens_used: 12 },
    });
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onTestProvider={onTest} />);
    // Click "Probar" en la fila LLM (índice 0).
    await user.click(screen.getAllByRole('button', { name: 'Probar' })[0]);
    // Modal abre con título "Probar LLM" + form.
    expect(await screen.findByRole('dialog', { name: /Probar LLM/i })).toBeInTheDocument();

    const prompt = screen.getByPlaceholderText(/Dame una idea/i);
    await user.type(prompt, 'Hola');
    await user.click(screen.getByRole('button', { name: 'Ejecutar' }));

    expect(onTest).toHaveBeenCalledWith('llm', expect.objectContaining({
      prompt: 'Hola',
    }));
    // El resultado se renderiza con el texto generado + elapsed_ms.
    expect(await screen.findByText('Hola desde Grok')).toBeInTheDocument();
    expect(screen.getByText(/234ms/)).toBeInTheDocument();
  });

  it('"Probar" muestra el error_class cuando ok=false (ej. rate-limited)', async () => {
    const onTest = vi.fn().mockResolvedValue({
      ok: false,
      modality: 'llm',
      provider: 'grok',
      model: 'grok-4.3',
      elapsed_ms: 89,
      error: 'grok rate-limited (retry-after=30)',
      error_class: 'ProviderRateLimited',
    });
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onTestProvider={onTest} />);
    await user.click(screen.getAllByRole('button', { name: 'Probar' })[0]);
    await user.type(screen.getByPlaceholderText(/Dame una idea/i), 'Hola');
    await user.click(screen.getByRole('button', { name: 'Ejecutar' }));
    expect(await screen.findByText('ProviderRateLimited')).toBeInTheDocument();
    expect(screen.getByText(/retry-after=30/)).toBeInTheDocument();
  });

  it('ofrece reuse-key cuando hay OTRA modalidad con el mismo provider + hint', async () => {
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} />);
    // Editar LLM (grok, hint=b12c). Image también es grok con hint xyz9
    // → debe ofrecer reusar la key de Image.
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    expect(screen.getByText(/Reusar API Key existente/i)).toBeInTheDocument();
    // El checkbox accesible expone la opción con el hint visible.
    expect(
      screen.getByRole('checkbox', { name: /Usar la key de Image.*xyz9/i }),
    ).toBeInTheDocument();
  });

  it('al marcar reuse-checkbox, el payload usa reuse_from_modality y NO secret_value', async () => {
    const onSave = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onSave={onSave} />);
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    // Marcar el checkbox "Usar la key de Image (••••xyz9)".
    const reuseCheckbox = screen.getByRole('checkbox', { name: /Usar la key de Image/i });
    await user.click(reuseCheckbox);
    // El input API Key queda disabled (UX: visualmente claro que no se usa).
    const apiKeyInput = screen.getByLabelText(/API Key del provider/i);
    expect(apiKeyInput).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(onSave).toHaveBeenCalledWith('llm', expect.objectContaining({
      reuse_from_modality: 'image',
    }));
    // CRÍTICO — la rotación de key NO debe disparar (mutuamente excluyente).
    expect(onSave.mock.calls[0][1].secret_value).toBeUndefined();
  });

  it('NO ofrece reuse cuando no hay otra modalidad con misma provider+hint', async () => {
    const isolated = [
      { modality: 'llm', provider: 'grok', model: 'grok-4.3', hint: 'b12c' },
      // Image existe pero sin hint configurado → no candidata para reuse.
      { modality: 'image', provider: 'grok', model: null, hint: null },
    ];
    const user = userEvent.setup();
    render(<AIProviders rows={isolated} />);
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    expect(screen.queryByText(/Reusar API Key existente/i)).not.toBeInTheDocument();
  });
});
