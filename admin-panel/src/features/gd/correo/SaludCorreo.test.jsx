import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getSaludCorreo: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { SaludCorreo } from './SaludCorreo.jsx';

const SALUD = {
  canales: [
    { id: 'c1', nombre: 'SMTP', ok_pct: 0.98, bounces: 2,
      errores_24h: 3, latencia_p50: 150, latencia_p99: 800,
      ultimo_error: 'TLS handshake' },
    { id: 'c2', nombre: 'IMAP', ok_pct: 0.7, bounces: 0,
      errores_24h: 12, latencia_p50: 300, latencia_p99: 2000 },
  ],
  totales: { recibidos: 500, enviados: 300, bounces: 2 },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getSaludCorreo.mockResolvedValue(SALUD);
});

describe('SaludCorreo', () => {
  it('sin permiso → aviso', () => {
    render(<SaludCorreo session={{}} roles={['gd.profesional']} />);
    expect(screen.getByTestId('cor-sal-no-perm')).toBeInTheDocument();
  });

  it('admin sistema ve KPIs + tabla', async () => {
    render(<SaludCorreo session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-sal-kpis'));
    expect(screen.getAllByTestId('cor-sal-row')).toHaveLength(2);
  });

  it('cambio de ventana refetch', async () => {
    const user = userEvent.setup();
    render(<SaludCorreo session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-sal-ventana'));
    await user.selectOptions(screen.getByTestId('cor-sal-ventana'), '7d');
    await waitFor(() => expect(api.getSaludCorreo).toHaveBeenCalledWith(
      expect.anything(), '7d',
    ));
  });

  it('error', async () => {
    api.getSaludCorreo.mockRejectedValue(new Error('e'));
    render(<SaludCorreo session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-sal-error'));
  });

  it('empty cuando canales vacíos', async () => {
    api.getSaludCorreo.mockResolvedValue({ canales: [], totales: { recibidos: 0, enviados: 0, bounces: 0 } });
    render(<SaludCorreo session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-sal-empty'));
  });

  it('auditor solo lee', async () => {
    render(<SaludCorreo session={{ token: 't' }} roles={['gd.auditor']} />);
    await waitFor(() => screen.getByTestId('cor-sal-kpis'));
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<SaludCorreo session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-sal-refresh'));
    api.getSaludCorreo.mockClear();
    await user.click(screen.getByTestId('cor-sal-refresh'));
    await waitFor(() => expect(api.getSaludCorreo).toHaveBeenCalled());
  });
});
