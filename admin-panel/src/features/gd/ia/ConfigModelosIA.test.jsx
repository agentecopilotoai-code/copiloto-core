import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getConfigModelosIa: vi.fn(),
  actualizarConfigModelosIa: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { ConfigModelosIA } from './ConfigModelosIA.jsx';

const CFG = {
  modelos: [
    { codigo: 'gpt-4', nombre: 'GPT-4', proveedor: 'openai', activo: true,
      temperatura: 0.7, max_tokens: 4096, guardrails: ['no_pii'],
      usos_permitidos: ['sugerencia', 'resumen'] },
    { codigo: 'claude-3', nombre: 'Claude 3', proveedor: 'anthropic',
      activo: false, temperatura: 0.5, max_tokens: 8192,
      guardrails: [], usos_permitidos: ['asistente'] },
  ],
  defaults: { sugerencia: 'gpt-4', resumen: 'gpt-4', busqueda: 'gpt-4',
              asistente: 'claude-3', pii: 'gpt-4' },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getConfigModelosIa.mockResolvedValue(CFG);
});

describe('ConfigModelosIA', () => {
  it('sin permiso muestra aviso', () => {
    api.getConfigModelosIa.mockResolvedValue({ modelos: [], defaults: {} });
    render(<ConfigModelosIA session={{}} roles={['gd.profesional']} />);
    expect(screen.getByTestId('ia-cfg-no-perm')).toBeInTheDocument();
  });

  it('admin sistema renderiza modelos + defaults', async () => {
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-defaults'));
    expect(screen.getAllByTestId('ia-cfg-modelo')).toHaveLength(2);
  });

  it('toggle activo + guardar', async () => {
    api.actualizarConfigModelosIa.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-activo-gpt-4'));
    await user.click(screen.getByTestId('ia-cfg-activo-gpt-4'));
    await user.click(screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await waitFor(() => expect(api.actualizarConfigModelosIa).toHaveBeenCalled());
    await waitFor(() => screen.getByTestId('ia-cfg-feedback-gpt-4'));
  });

  it('cambio de temperatura', async () => {
    api.actualizarConfigModelosIa.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-temp-gpt-4'));
    // range inputs disparan onChange con userEvent.type no funcionan bien;
    // usamos fireChange directo.
    const slider = screen.getByTestId('ia-cfg-temp-gpt-4');
    slider.focus();
    // Simulamos cambio via change event.
    slider.dispatchEvent(new Event('input', { bubbles: true }));
    await user.click(screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await waitFor(() => expect(api.actualizarConfigModelosIa).toHaveBeenCalled());
  });

  it('toggle de uso permitido', async () => {
    api.actualizarConfigModelosIa.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-uso-gpt-4-busqueda'));
    await user.click(screen.getByTestId('ia-cfg-uso-gpt-4-busqueda'));
    await user.click(screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await waitFor(() => expect(api.actualizarConfigModelosIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        codigo: 'gpt-4',
        usos_permitidos: expect.arrayContaining(['busqueda']),
      }),
    ));
  });

  it('guardrails editable', async () => {
    api.actualizarConfigModelosIa.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-guard-gpt-4'));
    fireEvent.change(screen.getByTestId('ia-cfg-guard-gpt-4'),
      { target: { value: 'no_pii, no_secrets' } });
    await user.click(screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await waitFor(() => expect(api.actualizarConfigModelosIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        guardrails: ['no_pii', 'no_secrets'],
      }),
    ));
  });

  it('error guardando muestra alerta', async () => {
    api.actualizarConfigModelosIa.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await user.click(screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await waitFor(() => expect(screen.getByTestId('ia-cfg-feedback-gpt-4').textContent).toMatch(/boom/));
  });

  it('error de carga', async () => {
    api.getConfigModelosIa.mockRejectedValue(new Error('e'));
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-error'));
  });

  it('refresh button', async () => {
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-refresh'));
    api.getConfigModelosIa.mockClear();
    await user.click(screen.getByTestId('ia-cfg-refresh'));
    await waitFor(() => expect(api.getConfigModelosIa).toHaveBeenCalled());
  });

  it('vacío muestra empty', async () => {
    api.getConfigModelosIa.mockResolvedValue({ modelos: [], defaults: {} });
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-empty'));
  });

  it('max_tokens cambia', async () => {
    api.actualizarConfigModelosIa.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-cfg-tokens-gpt-4'));
    fireEvent.change(screen.getByTestId('ia-cfg-tokens-gpt-4'),
      { target: { value: '8192' } });
    await user.click(screen.getByTestId('ia-cfg-guardar-gpt-4'));
    await waitFor(() => expect(api.actualizarConfigModelosIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ max_tokens: 8192 }),
    ));
  });

  it('admin_seguridad ve config R sin guardar', async () => {
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.admin_seguridad']} />);
    await waitFor(() => screen.getAllByTestId('ia-cfg-modelo'));
    expect(screen.queryByTestId('ia-cfg-activo-gpt-4')).toBeNull();
  });
});
