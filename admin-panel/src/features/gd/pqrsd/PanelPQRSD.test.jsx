import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getPQRSDDashboard: vi.fn(),
}));
import { getPQRSDDashboard } from '../services/gdApi.js';

import { PanelPQRSD } from './PanelPQRSD.jsx';

const DATA = {
  totales: { total: 124 },
  por_estado: { nueva: 5, asignada: 30, en_proyeccion: 12, en_revision: 6, cerrada: 70 },
  por_tipo: { P: 60, Q: 30, R: 20, S: 8, D: 6 },
  alertas: { proximas_vencer: 4, vencidas: 2, sin_asignar: 5 },
};

describe('PanelPQRSD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getPQRSDDashboard.mockResolvedValue(DATA);
  });

  it('renderiza KPIs cuando llega data', async () => {
    render(<PanelPQRSD session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('panel-kpis')).toBeInTheDocument());
    expect(screen.getByText('124')).toBeInTheDocument();
  });

  it('muestra distribución tipos', async () => {
    render(<PanelPQRSD session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('dist-tipos')).toBeInTheDocument());
    expect(screen.getByText(/Petición/)).toBeInTheDocument();
  });

  it('CTAs accesos rápidos llaman onNavigate', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<PanelPQRSD session={{ token: 't' }} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('link-sin-asignar'));
    await user.click(screen.getByTestId('link-sin-asignar'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/sin-asignar');
    await user.click(screen.getByTestId('link-vencidas'));
    expect(onNavigate).toHaveBeenLastCalledWith('/gd/pqrsd/vencidas');
  });

  it('cambio de periodo redispara fetch', async () => {
    render(<PanelPQRSD session={{ token: 't' }} />);
    await waitFor(() => expect(getPQRSDDashboard).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('panel-desde'), { target: { value: '2026-01-01' } });
    await waitFor(() => expect(getPQRSDDashboard).toHaveBeenCalledTimes(2));
  });

  it('error muestra alert', async () => {
    getPQRSDDashboard.mockRejectedValue(new Error('e'));
    render(<PanelPQRSD session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('refresh dispara fetch adicional', async () => {
    const user = userEvent.setup();
    render(<PanelPQRSD session={{ token: 't' }} />);
    await waitFor(() => expect(getPQRSDDashboard).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('panel-refresh'));
    expect(getPQRSDDashboard).toHaveBeenCalledTimes(2);
  });
});
