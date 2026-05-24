import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPerifericos: vi.fn(),
  getEstadoPerifericos: vi.fn(),
  crearPeriferico: vi.fn(),
  actualizarPeriferico: vi.fn(),
  inactivarPeriferico: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminPerifericos } from './AdminPerifericos.jsx';

const ROLES = ['gd.admin_sistema'];
const P = {
  id: 'p1', codigo: 'IMP-01', tipo: 'impresora', modelo: 'HP LaserJet',
  ubicacion: 'Ventanilla', activo: true, en_linea: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listPerifericos.mockResolvedValue({ items: [P], total: 1 });
  api.getEstadoPerifericos.mockResolvedValue({
    en_linea: 3, fuera_linea: 1, mantenimiento: 0,
  });
});

describe('AdminPerifericos', () => {
  it('sin permiso muestra warning', () => {
    render(<AdminPerifericos session={{ token: 't' }} roles={['gd.profesional']} />);
    expect(screen.getByTestId('per-no-perm')).toBeInTheDocument();
  });

  it('KPIs + tabla', async () => {
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('per-table')).toBeInTheDocument());
    expect(screen.getByTestId('per-estado')).toBeInTheDocument();
    expect(screen.getAllByTestId('per-kpi').length).toBeGreaterThanOrEqual(3);
  });

  it('empty', async () => {
    api.listPerifericos.mockResolvedValue({ items: [], total: 0 });
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('per-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listPerifericos.mockRejectedValue(new Error('e'));
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('filtros refetch', async () => {
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listPerifericos).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('per-filter-tipo'), { target: { value: 'escaner' } });
    fireEvent.change(screen.getByTestId('per-filter-ubic'), { target: { value: 'X' } });
    await waitFor(() => expect(api.listPerifericos).toHaveBeenCalledTimes(3));
  });

  it('crear periférico OK', async () => {
    api.crearPeriferico.mockResolvedValue({ id: 'p2' });
    const user = userEvent.setup();
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('per-nuevo'));
    fireEvent.change(screen.getByTestId('per-form-codigo'), { target: { value: 'IMP-02' } });
    fireEvent.change(screen.getByTestId('per-form-modelo'), { target: { value: 'Brother HL' } });
    fireEvent.change(screen.getByTestId('per-form-ubic'), { target: { value: 'Sec' } });
    await user.click(screen.getByTestId('per-form-submit'));
    await waitFor(() => expect(api.crearPeriferico).toHaveBeenCalled());
  });

  it('editar pre-llena', async () => {
    const user = userEvent.setup();
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('per-row'));
    await user.click(screen.getByTestId('per-editar'));
    expect(screen.getByTestId('per-form-modelo').value).toBe('HP LaserJet');
  });

  it('inactivar con motivo', async () => {
    api.inactivarPeriferico.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('per-row'));
    await user.click(screen.getByTestId('per-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'impresora fuera de servicio' } });
    await user.click(screen.getByTestId('per-inactivar-submit'));
    await waitFor(() => expect(api.inactivarPeriferico).toHaveBeenCalled());
  });

  it('crear error', async () => {
    api.crearPeriferico.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<AdminPerifericos session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('per-nuevo'));
    fireEvent.change(screen.getByTestId('per-form-codigo'), { target: { value: 'X' } });
    fireEvent.change(screen.getByTestId('per-form-modelo'), { target: { value: 'XX' } });
    await user.click(screen.getByTestId('per-form-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });
});
