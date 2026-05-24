import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listTRD: vi.fn(),
  getTRDVersionActual: vi.fn(),
  listVersionesTRD: vi.fn(),
  crearSerie: vi.fn(),
  crearSubserie: vi.fn(),
  crearTipoDocumental: vi.fn(),
  eliminarSerie: vi.fn(),
  nuevaVersionTRD: vi.fn(),
  aprobarVersionTRD: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { TablaTRD } from './TablaTRD.jsx';

const ROLES = ['gd.admin_documental'];
const SERIE = {
  id: 's1', codigo: 'S001', nombre: 'Contratos',
  subseries: [
    { id: 'ss1', codigo: 'S001.1', nombre: 'Servicios profesionales',
      tipos: [{ id: 't1', codigo: 'TD-01', nombre: 'Minuta' }] },
  ],
};

describe('TablaTRD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listTRD.mockResolvedValue({ items: [SERIE], total: 1 });
    api.getTRDVersionActual.mockResolvedValue({ numero: 2, aprobada_en: '2026-01-01' });
    api.listVersionesTRD.mockResolvedValue({ items: [{ id: 'v1' }] });
  });

  it('renderiza árbol de series', async () => {
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('trd-tree')).toBeInTheDocument());
    expect(screen.getByTestId('trd-serie')).toBeInTheDocument();
  });

  it('expandir muestra subseries y tipos', async () => {
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('trd-serie'));
    await user.click(screen.getByTestId('trd-serie-toggle'));
    expect(screen.getByTestId('trd-subserie')).toBeInTheDocument();
    expect(screen.getByTestId('trd-tipo')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listTRD.mockResolvedValue({ items: [], total: 0 });
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('trd-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listTRD.mockRejectedValue(new Error('e'));
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('botón nueva serie (con permiso) abre modal y submit OK', async () => {
    api.crearSerie.mockResolvedValue({ id: 's2' });
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('trd-nueva-serie'));
    expect(screen.getByTestId('trd-serie-modal')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('trd-serie-codigo'), { target: { value: 'S002' } });
    fireEvent.change(screen.getByTestId('trd-serie-nombre'), { target: { value: 'Convenios' } });
    await user.click(screen.getByTestId('trd-serie-submit'));
    await waitFor(() => expect(api.crearSerie).toHaveBeenCalled());
  });

  it('agregar subserie a serie expandida', async () => {
    api.crearSubserie.mockResolvedValue({ id: 'ss2' });
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('trd-serie'));
    await user.click(screen.getByTestId('trd-add-subserie'));
    fireEvent.change(screen.getByTestId('trd-subserie-codigo'), { target: { value: 'S001.2' } });
    fireEvent.change(screen.getByTestId('trd-subserie-nombre'), { target: { value: 'Obra' } });
    await user.click(screen.getByTestId('trd-subserie-submit'));
    await waitFor(() => expect(api.crearSubserie).toHaveBeenCalled());
  });

  it('agregar tipo en subserie expandida', async () => {
    api.crearTipoDocumental.mockResolvedValue({ id: 't2' });
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('trd-serie'));
    await user.click(screen.getByTestId('trd-serie-toggle'));
    await user.click(screen.getByTestId('trd-add-tipo'));
    fireEvent.change(screen.getByTestId('trd-tipo-nombre'), { target: { value: 'Adenda' } });
    await user.click(screen.getByTestId('trd-tipo-submit'));
    await waitFor(() => expect(api.crearTipoDocumental).toHaveBeenCalled());
  });

  it('inactivar serie con motivo', async () => {
    api.eliminarSerie.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('trd-serie'));
    await user.click(screen.getByTestId('trd-eliminar-serie'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'serie obsoleta por reorganización' } });
    await user.click(screen.getByTestId('trd-eliminar-submit'));
    await waitFor(() => expect(api.eliminarSerie).toHaveBeenCalled());
  });

  it('nueva versión TRD crea y aprueba', async () => {
    api.nuevaVersionTRD.mockResolvedValue({ id: 'v2' });
    api.aprobarVersionTRD.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('trd-nueva-version'));
    fireEvent.change(screen.getByLabelText(/Resumen de cambios/i), { target: { value: 'consolida cambios trimestre Q2' } });
    fireEvent.change(screen.getByTestId('trd-version-acta'), { target: { value: 'Acta 005/2026' } });
    await user.click(screen.getByTestId('trd-version-submit'));
    await waitFor(() => expect(api.nuevaVersionTRD).toHaveBeenCalled());
    await waitFor(() => expect(api.aprobarVersionTRD).toHaveBeenCalledWith({ token: 't' }, 'v2', { acta_comite: 'Acta 005/2026' }));
  });

  it('sin permiso oculta CTA admin', async () => {
    render(<TablaTRD session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('trd-tree'));
    expect(screen.queryByTestId('trd-nueva-serie')).toBeNull();
    expect(screen.queryByTestId('trd-add-subserie')).toBeNull();
  });

  it('refresh refetch', async () => {
    const user = userEvent.setup();
    render(<TablaTRD session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listTRD).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('trd-refresh'));
    expect(api.listTRD).toHaveBeenCalledTimes(2);
  });
});
