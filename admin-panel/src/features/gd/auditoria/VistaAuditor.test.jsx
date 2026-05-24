import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getResumenIntegridadAuditor: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { VistaAuditor } from './VistaAuditor.jsx';

const DATA = {
  hash_raiz: 'sha256-ABCDEF', calculado_en: '2026-05-23T10:00:00Z',
  total_registros: 12500, verificados: 12498, discrepancias: 2,
  porcentaje_integridad: 0.9998,
  por_entidad: [
    { entidad: 'pqrsd', total: 320, verificados: 320, discrepancias: 0, hash_raiz: 'aaaa' },
    { entidad: 'documento', total: 880, verificados: 878, discrepancias: 2, hash_raiz: 'bbbb' },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getResumenIntegridadAuditor.mockResolvedValue(DATA);
});

describe('VistaAuditor', () => {
  it('renderiza KPIs + tabla por entidad + hash raíz', async () => {
    render(<VistaAuditor session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('aud-vista-kpis')).toBeInTheDocument());
    expect(screen.getByTestId('aud-vista-hash-raiz').textContent).toMatch(/sha256-ABCDEF/);
    expect(screen.getByTestId('aud-vista-tabla')).toBeInTheDocument();
    expect(screen.getAllByTestId('aud-vista-row')).toHaveLength(2);
  });

  it('error', async () => {
    api.getResumenIntegridadAuditor.mockRejectedValue(new Error('e'));
    render(<VistaAuditor session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('sin discrepancias badge ok', async () => {
    api.getResumenIntegridadAuditor.mockResolvedValue({
      ...DATA, discrepancias: 0, porcentaje_integridad: 1.0,
    });
    render(<VistaAuditor session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('aud-vista-kpis')).toBeInTheDocument());
  });

  it('botones de herramientas navegan', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<VistaAuditor session={{ token: 't' }} onNavigate={onNavigate} />);
    await user.click(await screen.findByTestId('aud-vista-ir-auditoria'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/auditoria');
    await user.click(screen.getByTestId('aud-vista-ir-reportes'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/reportes');
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<VistaAuditor session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('aud-vista-kpis'));
    await user.click(screen.getByTestId('aud-vista-refresh'));
    expect(api.getResumenIntegridadAuditor).toHaveBeenCalledTimes(2);
  });

  it('sin por_entidad omite tabla', async () => {
    api.getResumenIntegridadAuditor.mockResolvedValue({ ...DATA, por_entidad: [] });
    render(<VistaAuditor session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('aud-vista-kpis'));
    expect(screen.queryByTestId('aud-vista-tabla')).toBeNull();
  });
});
