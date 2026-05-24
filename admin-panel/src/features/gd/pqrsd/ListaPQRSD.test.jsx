import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPQRSDFiltrados: vi.fn(),
}));
import { listPQRSDFiltrados } from '../services/gdApi.js';

import { ListaPQRSD } from './ListaPQRSD.jsx';

const ROW = {
  id: 'p1', numero_radicado: '2026-P-001',
  tipo: 'P', estado: 'asignada', asunto: 'Solicitud',
  dependencia_actual_nombre: 'Talento',
  dias_restantes: 8, termino_dias: 15,
};

describe('ListaPQRSD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('renderiza tabla con items + semaforo', async () => {
    listPQRSDFiltrados.mockResolvedValue({ items: [ROW], total: 1 });
    render(<ListaPQRSD session={{ token: 't' }} tenantSlug="x" />);
    await waitFor(() => expect(screen.getByTestId('lista-table')).toBeInTheDocument());
    expect(screen.getByText('2026-P-001')).toBeInTheDocument();
    expect(screen.getByTestId('vto-badge')).toBeInTheDocument();
  });

  it('empty', async () => {
    listPQRSDFiltrados.mockResolvedValue({ items: [], total: 0 });
    render(<ListaPQRSD session={{ token: 't' }} tenantSlug="x" />);
    await waitFor(() => expect(screen.getByTestId('lista-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    listPQRSDFiltrados.mockRejectedValue(new Error('e'));
    render(<ListaPQRSD session={{ token: 't' }} tenantSlug="x" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('cambiar filtros dispara fetch', async () => {
    listPQRSDFiltrados.mockResolvedValue({ items: [], total: 0 });
    render(<ListaPQRSD session={{ token: 't' }} tenantSlug="x" />);
    await waitFor(() => expect(listPQRSDFiltrados).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('lista-filter-estado'), { target: { value: 'cerrada' } });
    await waitFor(() => expect(listPQRSDFiltrados).toHaveBeenCalledTimes(2));
    const args = listPQRSDFiltrados.mock.calls.at(-1)[1];
    expect(args.estado).toBe('cerrada');
  });

  it('click en row navega a ficha', async () => {
    listPQRSDFiltrados.mockResolvedValue({ items: [ROW], total: 1 });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<ListaPQRSD session={{ token: 't' }} tenantSlug="x" onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('lista-row'));
    await user.click(screen.getByTestId('lista-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/p1');
  });

  it('filtrosIniciales se aplican al primer fetch', async () => {
    listPQRSDFiltrados.mockResolvedValue({ items: [], total: 0 });
    render(<ListaPQRSD session={{ token: 't' }} tenantSlug="x" filtrosIniciales={{ estado: 'nueva' }} />);
    await waitFor(() => expect(listPQRSDFiltrados).toHaveBeenCalled());
    const args = listPQRSDFiltrados.mock.calls[0][1];
    expect(args.estado).toBe('nueva');
  });
});
