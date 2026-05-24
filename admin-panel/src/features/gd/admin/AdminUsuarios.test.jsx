import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listUsuariosGd: vi.fn(),
  getUsuarioGd: vi.fn(),
  crearUsuarioGd: vi.fn(),
  actualizarUsuarioGd: vi.fn(),
  asignarRolUsuarioGd: vi.fn(),
  removerRolUsuarioGd: vi.fn(),
  inactivarUsuarioGd: vi.fn(),
  reactivarUsuarioGd: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminUsuarios } from './AdminUsuarios.jsx';

const ROLES = ['gd.admin_sistema'];
const U = {
  id: 'u1', nombre_completo: 'Ana López', email: 'ana@x.gov.co',
  dependencia_nombre: 'Talento', roles: ['gd.profesional'], estado: 'activo',
};

describe('AdminUsuarios', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listUsuariosGd.mockResolvedValue({ items: [U], total: 1 });
    api.getUsuarioGd.mockResolvedValue(U);
  });

  it('sin permiso muestra warning', () => {
    render(<AdminUsuarios session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('usr-no-perm')).toBeInTheDocument();
  });

  it('tabla con usuario', async () => {
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('usr-table')).toBeInTheDocument());
    expect(screen.getByText('Ana López')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listUsuariosGd.mockResolvedValue({ items: [], total: 0 });
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('usr-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listUsuariosGd.mockRejectedValue(new Error('e'));
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('filtros refetch', async () => {
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listUsuariosGd).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('usr-filter-q'), { target: { value: 'ana' } });
    fireEvent.change(screen.getByTestId('usr-filter-estado'), { target: { value: 'activo' } });
    fireEvent.change(screen.getByTestId('usr-filter-rol'), { target: { value: 'gd.profesional' } });
    await waitFor(() => expect(api.listUsuariosGd).toHaveBeenCalledTimes(4));
  });

  it('nuevo usuario submit OK', async () => {
    api.crearUsuarioGd.mockResolvedValue({ id: 'u2' });
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('usr-nuevo'));
    fireEvent.change(screen.getByTestId('usr-form-nombre'), { target: { value: 'Pedro X' } });
    fireEvent.change(screen.getByTestId('usr-form-email'), { target: { value: 'pedro@x.gov.co' } });
    await user.click(screen.getByTestId('usr-form-submit'));
    await waitFor(() => expect(api.crearUsuarioGd).toHaveBeenCalled());
  });

  it('crear error muestra alert', async () => {
    api.crearUsuarioGd.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('usr-nuevo'));
    fireEvent.change(screen.getByTestId('usr-form-nombre'), { target: { value: 'Nombre Largo' } });
    fireEvent.change(screen.getByTestId('usr-form-email'), { target: { value: 'a@b.co' } });
    await user.click(screen.getByTestId('usr-form-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('editar pre-llena form', async () => {
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('usr-row'));
    await user.click(screen.getByTestId('usr-editar'));
    expect(screen.getByTestId('usr-form-nombre').value).toBe('Ana López');
  });

  it('gestionar roles: asignar nuevo rol con motivo', async () => {
    api.asignarRolUsuarioGd.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('usr-row'));
    await user.click(screen.getByTestId('usr-roles'));
    await waitFor(() => screen.getByTestId('usr-roles-modal'));
    fireEvent.change(screen.getByLabelText(/Motivo de la asignación/i), { target: { value: 'asignación inicial trámite' } });
    await user.click(screen.getByTestId('usr-rol-asignar'));
    await waitFor(() => expect(api.asignarRolUsuarioGd).toHaveBeenCalled());
  });

  it('gestionar roles: remover rol existente', async () => {
    api.removerRolUsuarioGd.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('usr-row'));
    await user.click(screen.getByTestId('usr-roles'));
    await waitFor(() => screen.getByTestId('usr-rol-remover'));
    await user.click(screen.getByTestId('usr-rol-remover'));
    await waitFor(() => expect(api.removerRolUsuarioGd).toHaveBeenCalled());
  });

  it('inactivar con motivo', async () => {
    api.inactivarUsuarioGd.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('usr-row'));
    await user.click(screen.getByTestId('usr-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'separación del cargo formal' } });
    await user.click(screen.getByTestId('usr-inactivar-submit'));
    await waitFor(() => expect(api.inactivarUsuarioGd).toHaveBeenCalled());
  });

  it('reactivar (cuando estado=inactivo)', async () => {
    api.listUsuariosGd.mockResolvedValue({ items: [{ ...U, estado: 'inactivo' }], total: 1 });
    api.reactivarUsuarioGd.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminUsuarios session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('usr-row'));
    await user.click(screen.getByTestId('usr-reactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de reactivación/i), { target: { value: 'regreso al cargo formal' } });
    await user.click(screen.getByTestId('usr-reactivar-submit'));
    await waitFor(() => expect(api.reactivarUsuarioGd).toHaveBeenCalled());
  });
});
