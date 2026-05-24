import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  buscarExpedientes: vi.fn(),
  listTRD: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { BuscarExpedientes } from './BuscarExpedientes.jsx';

describe('BuscarExpedientes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listTRD.mockResolvedValue({ items: [{ id: 's1', codigo: 'S001', nombre: 'Contratos' }] });
  });

  it('renderiza form', async () => {
    render(<BuscarExpedientes session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('exp-buscar-form')).toBeInTheDocument());
  });

  it('select de serie pobla con TRD', async () => {
    render(<BuscarExpedientes session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('exp-buscar-serie')).toBeInTheDocument());
    const opts = screen.getByTestId('exp-buscar-serie').querySelectorAll('option');
    // 1 "todas" + 1 serie
    expect(opts.length).toBeGreaterThanOrEqual(2);
  });

  it('busca y muestra tabla', async () => {
    api.buscarExpedientes.mockResolvedValue({
      items: [{ id: 'e1', codigo: 'EXP-001', titulo: 'X', estado: 'abierto', fecha_apertura: '2026-01-01' }],
      total: 1,
    });
    const user = userEvent.setup();
    render(<BuscarExpedientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('exp-buscar-form'));
    fireEvent.change(screen.getByTestId('exp-buscar-q'), { target: { value: 'conv' } });
    await user.click(screen.getByTestId('exp-buscar-submit'));
    await waitFor(() => expect(screen.getByTestId('exp-buscar-table')).toBeInTheDocument());
    expect(screen.getByText('EXP-001')).toBeInTheDocument();
  });

  it('empty tras buscar', async () => {
    api.buscarExpedientes.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<BuscarExpedientes session={{ token: 't' }} />);
    await user.click(await screen.findByTestId('exp-buscar-submit'));
    await waitFor(() => expect(screen.getByTestId('exp-buscar-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.buscarExpedientes.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<BuscarExpedientes session={{ token: 't' }} />);
    await user.click(await screen.findByTestId('exp-buscar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('row click navega', async () => {
    api.buscarExpedientes.mockResolvedValue({
      items: [{ id: 'e1', codigo: 'EXP-001', titulo: 'X', estado: 'abierto' }],
      total: 1,
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BuscarExpedientes session={{ token: 't' }} onNavigate={onNavigate} />);
    await user.click(await screen.findByTestId('exp-buscar-submit'));
    await waitFor(() => screen.getByTestId('exp-buscar-row'));
    await user.click(screen.getByTestId('exp-buscar-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/expedientes/e1');
  });

  it('filtros adicionales', async () => {
    api.buscarExpedientes.mockResolvedValue({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<BuscarExpedientes session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('exp-buscar-form'));
    fireEvent.change(screen.getByTestId('exp-buscar-estado'), { target: { value: 'cerrado' } });
    fireEvent.change(screen.getByTestId('exp-buscar-dep'), { target: { value: 'Talento' } });
    fireEvent.change(screen.getByTestId('exp-buscar-desde'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByTestId('exp-buscar-hasta'), { target: { value: '2026-12-31' } });
    await user.click(screen.getByTestId('exp-buscar-submit'));
    await waitFor(() => expect(api.buscarExpedientes).toHaveBeenCalled());
    const payload = api.buscarExpedientes.mock.calls[0][1];
    expect(payload.estado).toBe('cerrado');
    expect(payload.dependencia).toBe('Talento');
    expect(payload.apertura_desde).toBe('2026-01-01');
  });
});
