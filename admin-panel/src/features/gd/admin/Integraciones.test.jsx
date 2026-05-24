import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listIntegraciones: vi.fn(),
  actualizarIntegracion: vi.fn(),
  probarIntegracion: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Integraciones } from './Integraciones.jsx';

const ROLES = ['gd.admin_sistema'];
const I = {
  codigo: 'smtp', nombre: 'Correo institucional', tipo: 'email',
  activa: true, ultima_prueba: '2026-05-20', config: { host: 'smtp.x.gov.co' },
};

describe('Integraciones', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listIntegraciones.mockResolvedValue([I]);
  });

  it('tabla', async () => {
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('int-table')).toBeInTheDocument());
  });

  it('empty', async () => {
    api.listIntegraciones.mockResolvedValue([]);
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('int-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listIntegraciones.mockRejectedValue(new Error('e'));
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('probar OK', async () => {
    api.probarIntegracion.mockResolvedValue({ latency_ms: 80 });
    const user = userEvent.setup();
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('int-row'));
    await user.click(screen.getByTestId('int-probar'));
    await waitFor(() => expect(screen.getByTestId('int-prueba-info').textContent).toMatch(/exitosa/));
  });

  it('probar error', async () => {
    api.probarIntegracion.mockRejectedValue(new Error('timeout'));
    const user = userEvent.setup();
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('int-row'));
    await user.click(screen.getByTestId('int-probar'));
    await waitFor(() => expect(screen.getByTestId('int-prueba-info').textContent).toMatch(/timeout/));
  });

  it('configurar JSON inválido', async () => {
    const user = userEvent.setup();
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('int-row'));
    await user.click(screen.getByTestId('int-editar'));
    fireEvent.change(screen.getByTestId('int-config-json'), { target: { value: 'no-es-json' } });
    await user.click(screen.getByTestId('int-editar-submit'));
    expect(screen.getByTestId('int-json-err')).toBeInTheDocument();
  });

  it('configurar OK', async () => {
    api.actualizarIntegracion.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Integraciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('int-row'));
    await user.click(screen.getByTestId('int-editar'));
    fireEvent.change(screen.getByTestId('int-config-json'), { target: { value: '{"host":"smtp.x.gov.co","port":587}' } });
    await user.click(screen.getByTestId('int-editar-submit'));
    await waitFor(() => expect(api.actualizarIntegracion).toHaveBeenCalled());
    const payload = api.actualizarIntegracion.mock.calls[0][2];
    expect(payload.config.port).toBe(587);
  });
});
