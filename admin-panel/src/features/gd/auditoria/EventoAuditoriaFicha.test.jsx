import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getEventoAuditoria: vi.fn(),
  verificarHashRegistro: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { EventoAuditoriaFicha } from './EventoAuditoriaFicha.jsx';

const EV = {
  id: 'e1', actor_email: 'admin@x.gov.co', actor_id: 'u1',
  accion: 'actualizar', entidad_tipo: 'pqrsd', entidad_id: 'p1',
  ip: '10.0.0.1', user_agent: 'Chrome', created_at: '2026-05-23T10:00:00Z',
  hash: 'sha256-current', hash_prev: 'sha256-prev',
  motivo: 'corrección de tipografía',
  payload_antes: { estado: 'asignada', responsable: 'u1' },
  payload_despues: { estado: 'cerrada', responsable: 'u1' },
  payload: { nota: 'OK' },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getEventoAuditoria.mockResolvedValue(EV);
});

describe('EventoAuditoriaFicha', () => {
  it('renderiza datos generales + diff', async () => {
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await waitFor(() => expect(screen.getByTestId('evt-general')).toBeInTheDocument());
    expect(screen.getByTestId('evt-hash').textContent).toMatch(/sha256-current/);
    expect(screen.getByTestId('evt-hash-prev').textContent).toMatch(/sha256-prev/);
    expect(screen.getByTestId('evt-motivo').textContent).toMatch(/tipografía/);
  });

  it('diff resalta cambios', async () => {
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await waitFor(() => expect(screen.getByTestId('evt-diff-table')).toBeInTheDocument());
    expect(screen.getAllByTestId('evt-diff-row')).toHaveLength(1);
  });

  it('diff sin cambios', async () => {
    api.getEventoAuditoria.mockResolvedValue({
      ...EV,
      payload_antes: { x: 1 }, payload_despues: { x: 1 },
    });
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await waitFor(() => expect(screen.getByTestId('evt-diff-nochange')).toBeInTheDocument());
  });

  it('diff sin antes/después muestra mensaje', async () => {
    api.getEventoAuditoria.mockResolvedValue({
      ...EV, payload_antes: null, payload_despues: null,
    });
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await waitFor(() => expect(screen.getByTestId('evt-diff')).toBeInTheDocument());
    expect(screen.getByText(/solo-lectura/)).toBeInTheDocument();
  });

  it('payload se muestra', async () => {
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await waitFor(() => expect(screen.getByTestId('evt-payload')).toBeInTheDocument());
  });

  it('verificar integridad OK', async () => {
    api.verificarHashRegistro.mockResolvedValue({ integro: true });
    const user = userEvent.setup();
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await user.click(await screen.findByTestId('evt-verificar'));
    await waitFor(() => expect(screen.getByTestId('evt-verif-info').textContent).toMatch(/íntegro/i));
  });

  it('verificar integridad falla', async () => {
    api.verificarHashRegistro.mockResolvedValue({ integro: false, detalle: 'hash mismatch' });
    const user = userEvent.setup();
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await user.click(await screen.findByTestId('evt-verificar'));
    await waitFor(() => expect(screen.getByTestId('evt-verif-info').textContent).toMatch(/comprometida|hash mismatch/i));
  });

  it('verificar lanza error', async () => {
    api.verificarHashRegistro.mockRejectedValue(new Error('network'));
    const user = userEvent.setup();
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await user.click(await screen.findByTestId('evt-verificar'));
    await waitFor(() => expect(screen.getByTestId('evt-verif-info').textContent).toMatch(/network/));
  });

  it('error de carga', async () => {
    api.getEventoAuditoria.mockRejectedValue(new Error('e'));
    render(<EventoAuditoriaFicha session={{ token: 't' }} eventoId="e1" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
