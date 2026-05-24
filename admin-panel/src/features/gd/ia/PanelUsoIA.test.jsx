import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getUsoIA: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { PanelUsoIA } from './PanelUsoIA.jsx';

const DATA = {
  total_llamadas: 1500, tokens_entrada: 1200000, tokens_salida: 350000,
  costo_total: 78500, usuarios_activos: 24,
  uso_sobre_limite: 0.42,
  por_funcionalidad: [
    { funcionalidad: 'asistente', llamadas: 800, tokens: 900000, costo: 45000 },
  ],
  por_usuario: [
    { email: 'a@x.gov.co', usuario_id: 'u1', llamadas: 200, tokens: 250000, costo: 12000, pct_limite: 0.95 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getUsoIA.mockResolvedValue(DATA);
});

describe('PanelUsoIA', () => {
  it('KPIs + tablas', async () => {
    render(<PanelUsoIA session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('ia-uso-kpis')).toBeInTheDocument());
    expect(screen.getByTestId('ia-uso-funcs')).toBeInTheDocument();
    expect(screen.getByTestId('ia-uso-usuarios')).toBeInTheDocument();
    expect(screen.getAllByTestId('ia-uso-kpi').length).toBeGreaterThanOrEqual(6);
  });

  it('error', async () => {
    api.getUsoIA.mockRejectedValue(new Error('e'));
    render(<PanelUsoIA session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('cambiar periodo refetch', async () => {
    render(<PanelUsoIA session={{ token: 't' }} />);
    await waitFor(() => expect(api.getUsoIA).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('ia-uso-desde'), { target: { value: '2026-01-01' } });
    await waitFor(() => expect(api.getUsoIA).toHaveBeenCalledTimes(2));
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<PanelUsoIA session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('ia-uso-kpis'));
    await user.click(screen.getByTestId('ia-uso-refresh'));
    expect(api.getUsoIA).toHaveBeenCalledTimes(2);
  });

  it('sin por_usuario omite tabla usuarios', async () => {
    api.getUsoIA.mockResolvedValue({ ...DATA, por_usuario: [] });
    render(<PanelUsoIA session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('ia-uso-kpis'));
    expect(screen.queryByTestId('ia-uso-usuarios')).toBeNull();
  });

  it('uso sobre límite alto marca warn', async () => {
    api.getUsoIA.mockResolvedValue({ ...DATA, uso_sobre_limite: 0.95 });
    render(<PanelUsoIA session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('ia-uso-kpis')).toBeInTheDocument());
  });
});
