import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  buscarRadicados: vi.fn(),
}));
import { buscarRadicados } from '../services/gdApi.js';

import { BuscarRadicados } from './BuscarRadicados.jsx';

describe('BuscarRadicados', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('estado inicial: filtros vacíos + empty hint', () => {
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" />);
    expect(screen.getByText(/Aplique filtros/)).toBeInTheDocument();
  });

  it('botón Buscar dispara fetch con filtros', async () => {
    buscarRadicados.mockResolvedValueOnce({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" />);
    await user.type(screen.getByTestId('filter-numero'), '2026');
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => expect(buscarRadicados).toHaveBeenCalled());
    const args = buscarRadicados.mock.calls[0][1];
    expect(args.numero).toBe('2026');
    expect(args.scope).toBeDefined();
  });

  it('resultados vacíos muestran mensaje específico', async () => {
    buscarRadicados.mockResolvedValueOnce({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" />);
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => expect(screen.getByTestId('buscar-vacio')).toBeInTheDocument());
  });

  it('lista resultados en la tabla', async () => {
    buscarRadicados.mockResolvedValueOnce({
      items: [{
        id: 'r1', numero_radicado: '2026-E-001',
        fecha_radicacion: '2026-05-23T10:00:00Z',
        estado: 'radicado', asunto: 'X',
        dependencia_actual_nombre: 'Dep',
      }],
      total: 1,
    });
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" />);
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => expect(screen.getByTestId('buscar-table')).toBeInTheDocument());
    expect(screen.getByText('2026-E-001')).toBeInTheDocument();
  });

  it('botón Limpiar resetea filtros y vuelve al hint', async () => {
    buscarRadicados.mockResolvedValueOnce({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" />);
    await user.type(screen.getByTestId('filter-numero'), '123');
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => expect(screen.getByTestId('buscar-vacio')).toBeInTheDocument());
    await user.click(screen.getByTestId('buscar-limpiar'));
    expect(screen.getByText(/Aplique filtros/)).toBeInTheDocument();
  });

  it('click en fila navega a la ficha', async () => {
    buscarRadicados.mockResolvedValueOnce({
      items: [{ id: 'r1', numero_radicado: 'X', fecha_radicacion: '2026-05-23T10:00:00Z', estado: 'radicado', asunto: 'X' }],
      total: 1,
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" onNavigate={onNavigate} />);
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => screen.getByTestId('buscar-table'));
    await user.click(screen.getByTestId('buscar-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/ventanilla/radicados/r1');
  });

  it('error muestra alert', async () => {
    buscarRadicados.mockRejectedValueOnce(new Error('net'));
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" />);
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('cambio de filtros se aplica antes de buscar', async () => {
    buscarRadicados.mockResolvedValueOnce({ items: [], total: 0 });
    const user = userEvent.setup();
    render(<BuscarRadicados session={{ token: 't' }} tenantSlug="x" canales={[{ id: 'c1', nombre: 'Web' }]} estados={['radicado']} dependencias={[{ id: 'd1', nombre: 'X' }]} />);
    fireEvent.change(screen.getByTestId('filter-estado'), { target: { value: 'radicado' } });
    fireEvent.change(screen.getByTestId('filter-canal'), { target: { value: 'c1' } });
    fireEvent.change(screen.getByTestId('filter-dep'), { target: { value: 'd1' } });
    fireEvent.change(screen.getByTestId('filter-desde'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByTestId('filter-vto'), { target: { value: 'proximo' } });
    fireEvent.change(screen.getByTestId('filter-serie'), { target: { value: 'S1' } });
    await user.click(screen.getByTestId('buscar-submit'));
    await waitFor(() => expect(buscarRadicados).toHaveBeenCalled());
    const args = buscarRadicados.mock.calls[0][1];
    expect(args.estado).toBe('radicado');
    expect(args.canal_id).toBe('c1');
    expect(args.dependencia).toBe('d1');
  });
});
