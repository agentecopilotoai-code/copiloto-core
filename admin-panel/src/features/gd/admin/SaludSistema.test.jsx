import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  getSaludSistema: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { SaludSistema } from './SaludSistema.jsx';

const SALUD = {
  uptime: '99.97%', latencia_p95_ms: 230,
  errores_24h: 5, sesiones_activas: 14,
  cola_notificaciones: 12, tareas_pendientes: 88,
  servicios: [
    { nombre: 'API GD', estado: 'ok', checked_at: '2026-05-24 11:00', latencia_ms: 80 },
    { nombre: 'SMTP', estado: 'degradado', checked_at: '2026-05-24 11:00', latencia_ms: 1500 },
  ],
  alertas: [
    { nivel: 'critica', titulo: 'SMTP lento', mensaje: 'p95 > 1s' },
  ],
};

describe('SaludSistema', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza KPIs + servicios + alertas', async () => {
    api.getSaludSistema.mockResolvedValue(SALUD);
    render(<SaludSistema session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('sal-kpis')).toBeInTheDocument());
    expect(screen.getByTestId('sal-servicios')).toBeInTheDocument();
    expect(screen.getByTestId('sal-alertas')).toBeInTheDocument();
    expect(screen.getAllByTestId('sal-kpi').length).toBeGreaterThanOrEqual(6);
  });

  it('alerta tone danger', async () => {
    api.getSaludSistema.mockResolvedValue({ ...SALUD, errores_24h: 100, cola_notificaciones: 5000 });
    render(<SaludSistema session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('sal-kpis')).toBeInTheDocument());
  });

  it('servicios down', async () => {
    api.getSaludSistema.mockResolvedValue({
      ...SALUD, servicios: [{ nombre: 'X', estado: 'down' }],
    });
    render(<SaludSistema session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('sal-servicios')).toBeInTheDocument());
  });

  it('sin servicios ni alertas', async () => {
    api.getSaludSistema.mockResolvedValue({
      uptime: '100%', latencia_p95_ms: 50, errores_24h: 0,
    });
    render(<SaludSistema session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('sal-kpis')).toBeInTheDocument());
    expect(screen.queryByTestId('sal-servicios')).toBeNull();
    expect(screen.queryByTestId('sal-alertas')).toBeNull();
  });

  it('error', async () => {
    api.getSaludSistema.mockRejectedValue(new Error('e'));
    render(<SaludSistema session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
