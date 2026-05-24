import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getConfigModelosIA: vi.fn(),
  actualizarConfigModelosIA: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { ConfigModelosIA } from './ConfigModelosIA.jsx';

const ROLES = ['gd.admin_sistema'];
const CFG = {
  asistente: { modelo: 'gpt-4o-mini', temperatura: 0.3, max_tokens: 2048, habilitado: true },
  resumen: { modelo: 'gpt-4o-mini', temperatura: 0.1, max_tokens: 1024, habilitado: true },
  guardrails: {
    bloquear_pii_salida: true,
    bloquear_lenguaje_ofensivo: true,
    registrar_prompts: true,
  },
  limite_mensual_tokens: 5000000,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getConfigModelosIA.mockResolvedValue(CFG);
});

describe('ConfigModelosIA', () => {
  it('sin permiso muestra warning', () => {
    render(<ConfigModelosIA session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('ia-cfg-no-perm')).toBeInTheDocument();
  });

  it('renderiza form + guardrails + límite', async () => {
    render(<ConfigModelosIA session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('ia-cfg-funcs')).toBeInTheDocument());
    expect(screen.getByTestId('ia-cfg-guardrails')).toBeInTheDocument();
    expect(screen.getByTestId('ia-cfg-limite')).toBeInTheDocument();
    expect(screen.getByTestId('ia-cfg-asistente-modelo').value).toBe('gpt-4o-mini');
  });

  it('error', async () => {
    api.getConfigModelosIA.mockRejectedValue(new Error('e'));
    render(<ConfigModelosIA session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('guardar con motivo OK', async () => {
    api.actualizarConfigModelosIA.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('ia-cfg-funcs'));
    fireEvent.change(screen.getByTestId('ia-cfg-asistente-modelo'), { target: { value: 'gpt-4o' } });
    fireEvent.change(screen.getByTestId('ia-cfg-asistente-temp'), { target: { value: '0.5' } });
    fireEvent.click(screen.getByTestId('ia-cfg-gr-pii'));   // desactivar
    fireEvent.change(screen.getByTestId('ia-cfg-limite-tokens'), { target: { value: '10000000' } });
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'upgrade modelo Q3' } });
    await user.click(screen.getByTestId('ia-cfg-guardar'));
    await waitFor(() => expect(api.actualizarConfigModelosIA).toHaveBeenCalled());
    const payload = api.actualizarConfigModelosIA.mock.calls[0][1];
    expect(payload.asistente.modelo).toBe('gpt-4o');
    expect(payload.asistente.temperatura).toBe(0.5);
    expect(payload.guardrails.bloquear_pii_salida).toBe(false);
    expect(payload.limite_mensual_tokens).toBe(10000000);
  });

  it('guardar error', async () => {
    api.actualizarConfigModelosIA.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('ia-cfg-funcs'));
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'cambio operativo' } });
    await user.click(screen.getByTestId('ia-cfg-guardar'));
    await waitFor(() => expect(screen.getByTestId('ia-cfg-info').textContent).toMatch(/boom/));
  });

  it('habilitar/deshabilitar funcionalidad', async () => {
    api.actualizarConfigModelosIA.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<ConfigModelosIA session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('ia-cfg-asistente-hab'));
    fireEvent.click(screen.getByTestId('ia-cfg-asistente-hab'));
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'desactivar asistente Q3' } });
    await user.click(screen.getByTestId('ia-cfg-guardar'));
    await waitFor(() => expect(api.actualizarConfigModelosIA).toHaveBeenCalled());
    const payload = api.actualizarConfigModelosIA.mock.calls[0][1];
    expect(payload.asistente.habilitado).toBe(false);
  });
});
