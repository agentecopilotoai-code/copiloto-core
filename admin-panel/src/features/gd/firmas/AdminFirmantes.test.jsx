import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listFirmantesAutorizados: vi.fn(),
  crearFirmanteAutorizado: vi.fn(),
  actualizarFirmanteAutorizado: vi.fn(),
  inactivarFirmanteAutorizado: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminFirmantes } from './AdminFirmantes.jsx';

const ROLES = ['gd.admin_sistema'];

const F1 = {
  id: 'a1', nombre: 'Pedro Pérez', cargo: 'Director',
  dependencia_nombre: 'Talento',
  tipos_habilitados: ['oficio', 'resolucion'],
  vigente_desde: '2026-01-01T00:00:00Z',
  vigente_hasta: '2027-01-01T00:00:00Z',
  activo: true,
};

describe('AdminFirmantes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listFirmantesAutorizados.mockResolvedValue({ items: [F1] });
  });

  it('sin permiso muestra warning', async () => {
    render(<AdminFirmantes session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('firmantes-no-perm')).toBeInTheDocument();
  });

  it('renderiza tabla con firmante', async () => {
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('firmantes-table')).toBeInTheDocument());
    expect(screen.getByText('Pedro Pérez')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listFirmantesAutorizados.mockResolvedValue({ items: [] });
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('firmantes-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listFirmantesAutorizados.mockRejectedValue(new Error('e'));
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('nuevo firmante OK', async () => {
    api.crearFirmanteAutorizado.mockResolvedValue({ id: 'a2' });
    const user = userEvent.setup();
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('firmantes-nuevo'));
    fireEvent.change(screen.getByTestId('firmantes-form-nombre'), { target: { value: 'Luisa M.' } });
    fireEvent.change(screen.getByTestId('firmantes-form-cargo'), { target: { value: 'Subdirectora' } });
    fireEvent.change(screen.getByTestId('firmantes-form-tipos'), { target: { value: 'oficio, acta' } });
    await user.click(screen.getByTestId('firmantes-form-submit'));
    await waitFor(() => expect(api.crearFirmanteAutorizado).toHaveBeenCalled());
    const payload = api.crearFirmanteAutorizado.mock.calls[0][1];
    expect(payload.tipos_habilitados).toEqual(['oficio', 'acta']);
  });

  it('crear error muestra alert', async () => {
    api.crearFirmanteAutorizado.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('firmantes-nuevo'));
    fireEvent.change(screen.getByTestId('firmantes-form-nombre'), { target: { value: 'AB' } });
    fireEvent.change(screen.getByTestId('firmantes-form-cargo'), { target: { value: 'CD' } });
    await user.click(screen.getByTestId('firmantes-form-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('editar firmante pre-llena form', async () => {
    const user = userEvent.setup();
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('firmantes-row'));
    await user.click(screen.getByTestId('firmantes-edit'));
    expect(screen.getByTestId('firmantes-form-nombre').value).toBe('Pedro Pérez');
  });

  it('inactivar submit OK', async () => {
    api.inactivarFirmanteAutorizado.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('firmantes-row'));
    await user.click(screen.getByTestId('firmantes-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'cese de funciones' } });
    await user.click(screen.getByTestId('firmantes-inactivar-submit'));
    await waitFor(() => expect(api.inactivarFirmanteAutorizado).toHaveBeenCalled());
  });

  it('fechas + dependencia se setean', async () => {
    api.crearFirmanteAutorizado.mockResolvedValue({ id: 'a2' });
    const user = userEvent.setup();
    render(<AdminFirmantes session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('firmantes-nuevo'));
    fireEvent.change(screen.getByTestId('firmantes-form-nombre'), { target: { value: 'Luisa M.' } });
    fireEvent.change(screen.getByTestId('firmantes-form-cargo'), { target: { value: 'Sub' } });
    fireEvent.change(screen.getByTestId('firmantes-form-dep'), { target: { value: 'd1' } });
    fireEvent.change(screen.getByTestId('firmantes-form-desde'), { target: { value: '2026-06-01' } });
    fireEvent.change(screen.getByTestId('firmantes-form-hasta'), { target: { value: '2027-06-01' } });
    await user.click(screen.getByTestId('firmantes-form-submit'));
    await waitFor(() => expect(api.crearFirmanteAutorizado).toHaveBeenCalled());
    const payload = api.crearFirmanteAutorizado.mock.calls[0][1];
    expect(payload.dependencia_id).toBe('d1');
    expect(payload.vigente_desde).toBe('2026-06-01');
  });
});
