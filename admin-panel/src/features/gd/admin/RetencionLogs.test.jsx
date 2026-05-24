import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getPoliticaRetencionLogs: vi.fn(),
  actualizarPoliticaRetencionLogs: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { RetencionLogs } from './RetencionLogs.jsx';

const ROLES = ['gd.admin_sistema'];
const POL = {
  retencion_auditoria_dias: 730,
  retencion_acceso_dias: 365,
  retencion_errores_dias: 90,
  retencion_integraciones_dias: 180,
};

describe('RetencionLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPoliticaRetencionLogs.mockResolvedValue(POL);
  });

  it('renderiza form prellenado', async () => {
    render(<RetencionLogs session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('log-card')).toBeInTheDocument());
    expect(screen.getByTestId('log-retencion_auditoria_dias').value).toBe('730');
  });

  it('error carga', async () => {
    api.getPoliticaRetencionLogs.mockRejectedValue(new Error('e'));
    render(<RetencionLogs session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('guardar política OK', async () => {
    api.actualizarPoliticaRetencionLogs.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<RetencionLogs session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('log-card'));
    fireEvent.change(screen.getByTestId('log-retencion_auditoria_dias'), { target: { value: '1095' } });
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'cumplimiento normativo nuevo' } });
    await user.click(screen.getByTestId('log-guardar'));
    await waitFor(() => expect(api.actualizarPoliticaRetencionLogs).toHaveBeenCalled());
    const payload = api.actualizarPoliticaRetencionLogs.mock.calls[0][1];
    expect(payload.retencion_auditoria_dias).toBe(1095);
  });

  it('guardar error muestra info', async () => {
    api.actualizarPoliticaRetencionLogs.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<RetencionLogs session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('log-card'));
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'cambio operativo válido' } });
    await user.click(screen.getByTestId('log-guardar'));
    await waitFor(() => expect(screen.getByTestId('log-info').textContent).toMatch(/boom/));
  });

  it('sin permiso campos disabled', async () => {
    render(<RetencionLogs session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('log-card'));
    expect(screen.getByTestId('log-retencion_auditoria_dias')).toBeDisabled();
    expect(screen.queryByTestId('log-guardar')).toBeNull();
  });
});
