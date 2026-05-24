import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listDocumentos: vi.fn(),
  subirArchivo: vi.fn(),
  crearDocumento: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Biblioteca } from './Biblioteca.jsx';

const ITEM = {
  id: 'd1', titulo: 'Resolución 001', tipo: 'acto_administrativo',
  version_actual: 1, estado: 'aprobado', autor_nombre: 'Ana',
  updated_at: '2026-05-20T10:00:00Z',
};

describe('Biblioteca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listDocumentos.mockResolvedValue({ items: [ITEM], total: 1 });
  });

  it('renderiza tabla con documento', async () => {
    render(<Biblioteca session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('bib-table')).toBeInTheDocument());
    expect(screen.getByText('Resolución 001')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listDocumentos.mockResolvedValue({ items: [], total: 0 });
    render(<Biblioteca session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('bib-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listDocumentos.mockRejectedValue(new Error('err'));
    render(<Biblioteca session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('filtros disparan refetch', async () => {
    render(<Biblioteca session={{ token: 't' }} />);
    await waitFor(() => expect(api.listDocumentos).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('bib-filter-q'), { target: { value: 'res' } });
    await waitFor(() => expect(api.listDocumentos).toHaveBeenCalledTimes(2));
    const args = api.listDocumentos.mock.calls.at(-1)[1];
    expect(args.q).toBe('res');
  });

  it('row click navega', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<Biblioteca session={{ token: 't' }} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('bib-row'));
    await user.click(screen.getByTestId('bib-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d1');
  });

  it('botón cargar (con permiso) abre modal', async () => {
    const user = userEvent.setup();
    render(<Biblioteca session={{ token: 't' }} roles={['gd.profesional']} />);
    await waitFor(() => screen.getByTestId('bib-cargar'));
    await user.click(screen.getByTestId('bib-cargar'));
    expect(screen.getByTestId('cargar-doc-modal')).toBeInTheDocument();
  });

  it('refresh refetch', async () => {
    const user = userEvent.setup();
    render(<Biblioteca session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('bib-table'));
    await user.click(screen.getByTestId('bib-refresh'));
    expect(api.listDocumentos).toHaveBeenCalledTimes(2);
  });

  it('filtros tipo + estado + fechas', async () => {
    render(<Biblioteca session={{ token: 't' }} />);
    await waitFor(() => expect(api.listDocumentos).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('bib-filter-tipo'), { target: { value: 'oficio' } });
    fireEvent.change(screen.getByTestId('bib-filter-estado'), { target: { value: 'borrador' } });
    fireEvent.change(screen.getByTestId('bib-filter-desde'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByTestId('bib-filter-hasta'), { target: { value: '2026-12-31' } });
    await waitFor(() => expect(api.listDocumentos).toHaveBeenCalledTimes(5));
  });
});
