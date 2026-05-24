import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listColaPendientesClasificacion: vi.fn(),
  clasificarRadicado: vi.fn(),
}));

import {
  listColaPendientesClasificacion,
  clasificarRadicado,
} from '../services/gdApi.js';

import { ColaVentanilla } from './ColaVentanilla.jsx';

const SESSION = { token: 't' };
const ROW = {
  id: 'r1', numero_radicado: '2026-E-001',
  fecha_radicacion: '2026-05-23T10:00:00Z',
  canal_nombre: 'Web', asunto: 'Solicitud',
};

describe('ColaVentanilla', () => {
  beforeEach(() => vi.clearAllMocks());

  it('muestra empty cuando no hay items', async () => {
    listColaPendientesClasificacion.mockResolvedValue({ items: [], total: 0 });
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByTestId('cola-empty')).toBeInTheDocument();
    });
  });

  it('lista items en la tabla', async () => {
    listColaPendientesClasificacion.mockResolvedValue({
      items: [ROW, { ...ROW, id: 'r2', numero_radicado: '2026-E-002' }],
      total: 2,
    });
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => {
      expect(screen.getAllByTestId('cola-row')).toHaveLength(2);
    });
    expect(screen.getByText('2026-E-001')).toBeInTheDocument();
  });

  it('error muestra alert', async () => {
    listColaPendientesClasificacion.mockRejectedValue(new Error('net'));
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  it('botón Clasificar abre drawer', async () => {
    listColaPendientesClasificacion.mockResolvedValue({ items: [ROW], total: 1 });
    const user = userEvent.setup();
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => screen.getByTestId('cola-table'));
    await user.click(screen.getByTestId('cola-clasificar-btn'));
    expect(screen.getByTestId('clasificar-drawer')).toBeInTheDocument();
  });

  it('drawer submit dispara clasificarRadicado', async () => {
    listColaPendientesClasificacion.mockResolvedValue({ items: [ROW], total: 1 });
    clasificarRadicado.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => screen.getByTestId('cola-table'));
    await user.click(screen.getByTestId('cola-clasificar-btn'));
    fireEvent.change(screen.getByTestId('drawer-tipo'), { target: { value: 'pqrsd' } });
    await user.click(screen.getByTestId('drawer-clasificar-submit'));
    await waitFor(() =>
      expect(clasificarRadicado).toHaveBeenCalledWith(
        SESSION, 'r1', expect.objectContaining({ tipo_clasificacion: 'pqrsd' }),
      ),
    );
  });

  it('refresh dispara nuevo fetch', async () => {
    listColaPendientesClasificacion.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => expect(listColaPendientesClasificacion).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('cola-refresh'));
    expect(listColaPendientesClasificacion).toHaveBeenCalledTimes(2);
  });

  it('filtros se aplican (cambio de canal)', async () => {
    listColaPendientesClasificacion.mockResolvedValue({ items: [], total: 0 });
    render(<ColaVentanilla session={SESSION} />);
    await waitFor(() => screen.getByTestId('cola-filter-canal'));
    fireEvent.change(screen.getByTestId('cola-filter-canal'), { target: { value: 'presencial' } });
    await waitFor(() => {
      const last = listColaPendientesClasificacion.mock.calls.at(-1)[1];
      expect(last.canal_id).toBe('presencial');
    });
  });
});
