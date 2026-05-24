import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listAnulacionesPendientes: vi.fn(),
  aprobarAnulacion: vi.fn(),
  rechazarAnulacion: vi.fn(),
}));
import {
  listAnulacionesPendientes,
  aprobarAnulacion,
  rechazarAnulacion,
} from '../services/gdApi.js';

import { AnulacionesPendientes } from './AnulacionesPendientes.jsx';

const ROW = {
  id: 's1',
  numero_radicado: '2026-E-001',
  solicitante_user_id: 'u-other',
  solicitante_nombre: 'Pedro G',
  motivo: 'Duplicado del 2026-E-000990',
  fecha_solicitud: '2026-05-22T10:00:00Z',
};

describe('AnulacionesPendientes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listAnulacionesPendientes.mockResolvedValue({ items: [ROW], total: 1 });
  });

  it('lista solicitudes pendientes', async () => {
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('anul-table'));
    expect(screen.getByText('2026-E-001')).toBeInTheDocument();
  });

  it('empty cuando no hay solicitudes', async () => {
    listAnulacionesPendientes.mockResolvedValue({ items: [], total: 0 });
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('anul-empty'));
  });

  it('error muestra alert', async () => {
    listAnulacionesPendientes.mockRejectedValue(new Error('net'));
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('si el current user es el solicitante, no muestra botones', async () => {
    render(<AnulacionesPendientes session={{ token: 't' }} currentUserId="u-other" />);
    await waitFor(() => screen.getByTestId('anul-table'));
    expect(screen.queryByTestId('anul-aprobar-btn')).toBeNull();
    expect(screen.getByText(/No puede aprobar/)).toBeInTheDocument();
  });

  it('aprobar abre modal + confirma', async () => {
    aprobarAnulacion.mockResolvedValueOnce({});
    const user = userEvent.setup();
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('anul-table'));
    await user.click(screen.getByTestId('anul-aprobar-btn'));
    expect(screen.getByTestId('anul-modal')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('anul-observacion'), { target: { value: 'OK' } });
    await user.click(screen.getByTestId('anul-confirm'));
    await waitFor(() => expect(aprobarAnulacion).toHaveBeenCalledWith({ token: 't' }, 's1', 'OK'));
  });

  it('rechazar dispara rechazarAnulacion', async () => {
    rechazarAnulacion.mockResolvedValueOnce({});
    const user = userEvent.setup();
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('anul-table'));
    await user.click(screen.getByTestId('anul-rechazar-btn'));
    await user.click(screen.getByTestId('anul-confirm'));
    await waitFor(() => expect(rechazarAnulacion).toHaveBeenCalled());
  });

  it('refresh redispara fetch', async () => {
    const user = userEvent.setup();
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => expect(listAnulacionesPendientes).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('anul-refresh'));
    expect(listAnulacionesPendientes).toHaveBeenCalledTimes(2);
  });

  it('error en aprobar deja al modal abierto con mensaje', async () => {
    aprobarAnulacion.mockRejectedValueOnce(new Error('fail'));
    const user = userEvent.setup();
    render(<AnulacionesPendientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('anul-table'));
    await user.click(screen.getByTestId('anul-aprobar-btn'));
    await user.click(screen.getByTestId('anul-confirm'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByTestId('anul-modal')).toBeInTheDocument();
  });
});
