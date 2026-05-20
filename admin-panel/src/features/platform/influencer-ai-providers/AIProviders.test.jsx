import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AIProviders } from './AIProviders.jsx';


const ROWS = [
  { modality: 'llm', provider: 'grok', model: 'grok-4.3', hint: 'b12c', rotated_at: '2026-05-10 14:30' },
  { modality: 'image', provider: 'grok', model: 'grok-imagine-image', hint: 'xyz9', rotated_at: '2026-05-10 14:32' },
];


describe('<AIProviders/> (UI-INFLU-015)', () => {
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

  it('Guardar dispara onSave con payload correcto (incluye api_key si fue typed)', async () => {
    const onSave = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onSave={onSave} />);
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    const apiKeyInput = screen.getByPlaceholderText(/Se sobrescribirá la actual/i);
    await user.type(apiKeyInput, 'new-key-xyz');
    await user.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(onSave).toHaveBeenCalledWith('llm', expect.objectContaining({ api_key: 'new-key-xyz' }));
  });

  it('Guardar sin api_key no la incluye en el payload', async () => {
    const onSave = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onSave={onSave} />);
    await user.click(screen.getAllByRole('button', { name: 'Editar' })[0]);
    await user.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(onSave).toHaveBeenCalled();
    expect(onSave.mock.calls[0][1].api_key).toBeUndefined();
  });

  it('"Probar" muestra resultado con elapsed_ms', async () => {
    const onTest = vi.fn().mockResolvedValue({ ok: true, elapsed_ms: 320 });
    const user = userEvent.setup();
    render(<AIProviders rows={ROWS} onTestProvider={onTest} />);
    await user.click(screen.getAllByRole('button', { name: 'Probar' })[0]);
    expect(await screen.findByText(/OK · 320ms/)).toBeInTheDocument();
  });
});
