import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getMiBuzon: vi.fn(),
}));
import { getMiBuzon } from '../services/gdApi.js';

import { MiBuzon } from './MiBuzon.jsx';

const ITEMS = [
  {
    id: 'i1', tipo: 'pqrsd', titulo: 'PQRSD #2026-001',
    sub_titulo: 'Solicitud certificado', estado: 'asignada',
    fecha: '2026-05-23T10:00:00Z',
    descripcion: 'Tercero solicita certificado…',
    ruta_ficha: '/gd/pqrsd/p1',
  },
  {
    id: 'i2', tipo: 'tarea', titulo: 'Revisar respuesta',
    sub_titulo: 'PQRSD #2026-002', estado: 'pendiente',
    fecha: '2026-05-23T11:00:00Z',
  },
];

describe('MiBuzon', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMiBuzon.mockResolvedValue({
      items: ITEMS, contadores: { pqrsd: 2, tareas: 5 }, total: 2,
    });
  });

  it('renderiza layout 3-columnas', async () => {
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('mi-buzon-layout')).toBeInTheDocument());
    expect(screen.getByTestId('buzon-carpetas')).toBeInTheDocument();
    expect(screen.getByTestId('buzon-lista')).toBeInTheDocument();
    expect(screen.getByTestId('buzon-detalle')).toBeInTheDocument();
  });

  it('lista items con conteo', async () => {
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getAllByTestId('buzon-item').length).toBe(2));
    expect(screen.getByText(/2 ítem/)).toBeInTheDocument();
  });

  it('carpeta tareas muestra count 5', async () => {
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('carpeta-pqrsd'));
    expect(screen.getByTestId('carpeta-tareas').textContent).toMatch(/5/);
  });

  it('cambio de carpeta dispara nuevo fetch', async () => {
    const user = userEvent.setup();
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => expect(getMiBuzon).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('carpeta-tareas'));
    await waitFor(() => expect(getMiBuzon).toHaveBeenCalledTimes(2));
  });

  it('click en item muestra detalle con título', async () => {
    const user = userEvent.setup();
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => screen.getAllByTestId('buzon-item'));
    await user.click(screen.getAllByTestId('buzon-item')[1]);
    // El detalle es el panel derecho; busca el título dentro de él
    expect(screen.getByTestId('buzon-detalle').textContent).toContain('Revisar respuesta');
  });

  it('botón Abrir ficha navega', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<MiBuzon session={{ token: 't' }} onNavigate={onNavigate} />);
    await waitFor(() => screen.getAllByTestId('buzon-item'));
    // primer item viene seleccionado por default y tiene ruta_ficha
    await user.click(screen.getByTestId('abrir-ficha'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/p1');
  });

  it('item tipo=tarea muestra botón Ver tarea', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<MiBuzon session={{ token: 't' }} onNavigate={onNavigate} />);
    await waitFor(() => screen.getAllByTestId('buzon-item'));
    await user.click(screen.getAllByTestId('buzon-item')[1]);
    await user.click(screen.getByTestId('abrir-tarea'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/tareas/i2');
  });

  it('empty muestra mensaje cuando no hay items', async () => {
    getMiBuzon.mockResolvedValue({ items: [], contadores: {}, total: 0 });
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('buzon-empty')).toBeInTheDocument());
  });

  it('error muestra alert', async () => {
    getMiBuzon.mockRejectedValue(new Error('boom'));
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('refresh dispara nuevo fetch', async () => {
    const user = userEvent.setup();
    render(<MiBuzon session={{ token: 't' }} />);
    await waitFor(() => expect(getMiBuzon).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('buzon-refresh'));
    expect(getMiBuzon).toHaveBeenCalledTimes(2);
  });
});
