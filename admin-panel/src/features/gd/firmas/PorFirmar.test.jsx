import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPorFirmar: vi.fn(),
  firmarDocumento: vi.fn(),
  rechazarFirmaDocumento: vi.fn(),
  registrarFirmaEscaneada: vi.fn(),
  subirArchivo: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { PorFirmar } from './PorFirmar.jsx';

const ROLES = ['gd.firmante'];

const ITEM = {
  id: 'f1', documento_id: 'd1', titulo: 'Oficio 02', tipo: 'oficio',
  solicitante_nombre: 'Ana', solicitado_en: '2026-05-20T10:00:00Z',
};

describe('PorFirmar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listPorFirmar.mockResolvedValue({ items: [ITEM], total: 1 });
  });

  it('sin permiso muestra warning', async () => {
    render(<PorFirmar session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('firmar-no-perm')).toBeInTheDocument();
  });

  it('tabla por firmar', async () => {
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('firmar-table')).toBeInTheDocument());
  });

  it('empty', async () => {
    api.listPorFirmar.mockResolvedValue({ items: [], total: 0 });
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('firmar-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listPorFirmar.mockRejectedValue(new Error('e'));
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('click en título navega', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('firmar-row-link'));
    await user.click(screen.getByTestId('firmar-row-link'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d1');
  });

  it('botón Firmar digital invoca API', async () => {
    api.firmarDocumento.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('firmar-row'));
    await user.click(screen.getByTestId('firmar-btn-digital'));
    await waitFor(() => expect(api.firmarDocumento).toHaveBeenCalledWith({ token: 't' }, 'd1', {}));
  });

  it('botón Escaneada abre modal', async () => {
    const user = userEvent.setup();
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('firmar-row'));
    await user.click(screen.getByTestId('firmar-btn-escaneada'));
    expect(screen.getByTestId('firma-escaneada-modal')).toBeInTheDocument();
  });

  it('botón Rechazar abre modal + submit OK', async () => {
    api.rechazarFirmaDocumento.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('firmar-row'));
    await user.click(screen.getByTestId('firmar-btn-rechazar'));
    expect(screen.getByTestId('firmar-rechazo-modal')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Motivo del rechazo/i), { target: { value: 'requiere corrección formal' } });
    await user.click(screen.getByTestId('firmar-rechazo-submit'));
    await waitFor(() => expect(api.rechazarFirmaDocumento).toHaveBeenCalled());
  });

  it('filtro tipo + dependencia disparan refetch', async () => {
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listPorFirmar).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('firmar-filter-tipo'), { target: { value: 'oficio' } });
    await waitFor(() => expect(api.listPorFirmar).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByTestId('firmar-filter-dep'), { target: { value: 'd1' } });
    await waitFor(() => expect(api.listPorFirmar).toHaveBeenCalledTimes(3));
  });

  it('refresh refetch', async () => {
    const user = userEvent.setup();
    render(<PorFirmar session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('firmar-table'));
    await user.click(screen.getByTestId('firmar-refresh'));
    expect(api.listPorFirmar).toHaveBeenCalledTimes(2);
  });
});
