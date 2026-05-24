import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listParametros: vi.fn(),
  actualizarParametro: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminParametros } from './AdminParametros.jsx';

const ROLES = ['gd.admin_sistema'];
const PARAMS = [
  { codigo: 'PQRSD_DIAS_HABILES', descripcion: 'Días hábiles base PQRSD', valor: 15, tipo: 'number' },
  { codigo: 'PQRSD_NOTIFICAR', descripcion: 'Notificar nuevo', valor: true, tipo: 'boolean' },
  { codigo: 'PQRSD_FORMATO', descripcion: 'Formato número', valor: 'YYYY-NN', tipo: 'string' },
];

describe('AdminParametros', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listParametros.mockResolvedValue({ items: PARAMS });
  });

  it('renderiza tabla', async () => {
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('par-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('par-row')).toHaveLength(3);
  });

  it('empty', async () => {
    api.listParametros.mockResolvedValue({ items: [] });
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('par-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listParametros.mockRejectedValue(new Error('e'));
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('editar number guarda Number', async () => {
    api.actualizarParametro.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getAllByTestId('par-row'));
    await user.click(screen.getAllByTestId('par-editar')[0]);
    fireEvent.change(screen.getByTestId('par-editar-valor'), { target: { value: '20' } });
    await user.click(screen.getByTestId('par-editar-submit'));
    await waitFor(() => expect(api.actualizarParametro).toHaveBeenCalled());
    const payload = api.actualizarParametro.mock.calls[0][2];
    expect(payload.valor).toBe(20);
  });

  it('editar boolean guarda Boolean', async () => {
    api.actualizarParametro.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getAllByTestId('par-row'));
    await user.click(screen.getAllByTestId('par-editar')[1]);
    fireEvent.change(screen.getByTestId('par-editar-valor'), { target: { value: 'false' } });
    await user.click(screen.getByTestId('par-editar-submit'));
    await waitFor(() => expect(api.actualizarParametro).toHaveBeenCalled());
    const payload = api.actualizarParametro.mock.calls[0][2];
    expect(payload.valor).toBe(false);
  });

  it('editar error', async () => {
    api.actualizarParametro.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getAllByTestId('par-row'));
    await user.click(screen.getAllByTestId('par-editar')[0]);
    await user.click(screen.getByTestId('par-editar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<AdminParametros session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('par-table'));
    await user.click(screen.getByTestId('par-refresh'));
    expect(api.listParametros).toHaveBeenCalledTimes(2);
  });

  it('sin permiso oculta editar', async () => {
    render(<AdminParametros session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('par-table'));
    expect(screen.queryByTestId('par-editar')).toBeNull();
  });
});
