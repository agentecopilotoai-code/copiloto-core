import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  cerrarExpediente: vi.fn(),
  transferirExpediente: vi.fn(),
  getActaCierreExpediente: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { CerrarExpedienteModal } from './CerrarExpedienteModal.jsx';

describe('CerrarExpedienteModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza form de cierre', () => {
    render(<CerrarExpedienteModal session={{ token: 't' }} expedienteId="e1" onClose={() => {}} />);
    expect(screen.getByTestId('exp-cerrar-modal')).toBeInTheDocument();
    expect(screen.getByTestId('exp-cerrar-acta')).toBeInTheDocument();
  });

  it('submit deshabilitado sin acta/motivo', () => {
    render(<CerrarExpedienteModal session={{ token: 't' }} expedienteId="e1" onClose={() => {}} />);
    expect(screen.getByTestId('exp-cerrar-submit')).toBeDisabled();
  });

  it('cierre simple sin transferir', async () => {
    api.cerrarExpediente.mockResolvedValue({ ok: true });
    api.getActaCierreExpediente.mockResolvedValue({
      numero: 'A001', emitida_en: '2026-05-20T10:00:00Z',
      hash_indice: 'sha256-abc',
    });
    const user = userEvent.setup();
    render(<CerrarExpedienteModal session={{ token: 't' }} expedienteId="e1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('exp-cerrar-acta'), { target: { value: 'Acta 23/2026' } });
    fireEvent.change(screen.getByLabelText(/Motivo \/ contexto/i), { target: { value: 'cumplimiento objeto contractual' } });
    await user.click(screen.getByTestId('exp-cerrar-submit'));
    await waitFor(() => expect(api.cerrarExpediente).toHaveBeenCalled());
    expect(api.transferirExpediente).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId('exp-acta-hash').textContent).toMatch(/sha256-abc/));
  });

  it('cierre con transferencia inmediata', async () => {
    api.cerrarExpediente.mockResolvedValue({ ok: true });
    api.transferirExpediente.mockResolvedValue({ ok: true });
    api.getActaCierreExpediente.mockResolvedValue({ numero: 'A001' });
    const user = userEvent.setup();
    render(<CerrarExpedienteModal session={{ token: 't' }} expedienteId="e1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('exp-cerrar-acta'), { target: { value: 'Acta 23/2026' } });
    fireEvent.change(screen.getByLabelText(/Motivo \/ contexto/i), { target: { value: 'finalización proyecto Q2' } });
    fireEvent.click(screen.getByTestId('exp-cerrar-transferir'));
    fireEvent.change(screen.getByTestId('exp-cerrar-destino'), { target: { value: 'archivo_historico' } });
    await user.click(screen.getByTestId('exp-cerrar-submit'));
    await waitFor(() => expect(api.transferirExpediente).toHaveBeenCalled());
    const transferPayload = api.transferirExpediente.mock.calls[0][2];
    expect(transferPayload.destino).toBe('archivo_historico');
  });

  it('error al cerrar muestra alert', async () => {
    api.cerrarExpediente.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<CerrarExpedienteModal session={{ token: 't' }} expedienteId="e1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('exp-cerrar-acta'), { target: { value: 'A1' } });
    fireEvent.change(screen.getByLabelText(/Motivo \/ contexto/i), { target: { value: 'motivo válido para cerrar' } });
    await user.click(screen.getByTestId('exp-cerrar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('finalizar invoca onSuccess', async () => {
    api.cerrarExpediente.mockResolvedValue({ ok: true });
    api.getActaCierreExpediente.mockResolvedValue({ numero: 'A001' });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<CerrarExpedienteModal session={{ token: 't' }} expedienteId="e1" onClose={() => {}} onSuccess={onSuccess} />);
    fireEvent.change(screen.getByTestId('exp-cerrar-acta'), { target: { value: 'A1' } });
    fireEvent.change(screen.getByLabelText(/Motivo \/ contexto/i), { target: { value: 'cierre por finalización contrato' } });
    await user.click(screen.getByTestId('exp-cerrar-submit'));
    await waitFor(() => screen.getByTestId('exp-cerrar-finalizar'));
    await user.click(screen.getByTestId('exp-cerrar-finalizar'));
    expect(onSuccess).toHaveBeenCalled();
  });
});
