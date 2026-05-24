import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listTVD: vi.fn(),
  actualizarTVD: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { TablaTVD } from './TablaTVD.jsx';

const ROLES = ['gd.admin_documental'];
const FILA = {
  id: 'r1', serie_codigo: 'S001', serie_nombre: 'Contratos',
  subserie_codigo: 'S001.1',
  retencion_ag: 2, retencion_ac: 8, disposicion: 'CT',
  procedimiento: 'Conservar en repositorio digital.',
};

describe('TablaTVD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listTVD.mockResolvedValue({ items: [FILA], total: 1 });
  });

  it('tabla con fila', async () => {
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('tvd-table')).toBeInTheDocument());
    expect(screen.getByText('S001 — Contratos')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listTVD.mockResolvedValue({ items: [], total: 0 });
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('tvd-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listTVD.mockRejectedValue(new Error('e'));
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('filtro q dispara refetch', async () => {
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listTVD).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('tvd-filter-q'), { target: { value: 'cont' } });
    await waitFor(() => expect(api.listTVD).toHaveBeenCalledTimes(2));
  });

  it('editar con permiso abre modal y submit OK', async () => {
    api.actualizarTVD.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('tvd-row'));
    await user.click(screen.getByTestId('tvd-editar'));
    fireEvent.change(screen.getByTestId('tvd-ag'), { target: { value: '3' } });
    fireEvent.change(screen.getByTestId('tvd-ac'), { target: { value: '10' } });
    fireEvent.change(screen.getByTestId('tvd-disposicion'), { target: { value: 'S' } });
    fireEvent.change(screen.getByTestId('tvd-proc'), { target: { value: 'Selección por muestreo.' } });
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'ajuste por nueva normativa' } });
    await user.click(screen.getByTestId('tvd-editar-submit'));
    await waitFor(() => expect(api.actualizarTVD).toHaveBeenCalled());
    const payload = api.actualizarTVD.mock.calls[0][2];
    expect(payload.retencion_ag).toBe(3);
    expect(payload.disposicion).toBe('S');
  });

  it('editar error muestra alert', async () => {
    api.actualizarTVD.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('tvd-row'));
    await user.click(screen.getByTestId('tvd-editar'));
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'cambio operativo' } });
    await user.click(screen.getByTestId('tvd-editar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('sin permiso oculta editar', async () => {
    render(<TablaTVD session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('tvd-table'));
    expect(screen.queryByTestId('tvd-editar')).toBeNull();
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<TablaTVD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('tvd-table'));
    await user.click(screen.getByTestId('tvd-refresh'));
    expect(api.listTVD).toHaveBeenCalledTimes(2);
  });
});
