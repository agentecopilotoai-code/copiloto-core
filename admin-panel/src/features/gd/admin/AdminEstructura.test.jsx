import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getEstructuraOrganica: vi.fn(),
  crearDependencia: vi.fn(),
  actualizarDependencia: vi.fn(),
  reubicarDependencia: vi.fn(),
  inactivarDependencia: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminEstructura } from './AdminEstructura.jsx';

const ROLES = ['gd.admin_sistema'];
const TREE = {
  // version_id requerido por el form de Dependencia (campo
  // `version_estructura_id` del schema CrearDependencia del backend).
  version_id: 'ver-est-uuid-1',
  dependencias: [{
    id: 'd1', codigo: 'D01', nombre: 'Despacho', activa: true,
    jefe_nombre: 'Pedro X',
    hijas: [{ id: 'd2', codigo: 'D01.1', nombre: 'Talento', activa: true }],
  }],
};

describe('AdminEstructura', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getEstructuraOrganica.mockResolvedValue(TREE);
  });

  it('renderiza árbol', async () => {
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('est-tree')).toBeInTheDocument());
  });

  it('expandir muestra hijas', async () => {
    const user = userEvent.setup();
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('est-tree'));
    await user.click(screen.getByTestId('est-nodo-toggle'));
    expect(screen.getAllByTestId('est-nodo').length).toBeGreaterThan(1);
  });

  it('empty', async () => {
    api.getEstructuraOrganica.mockResolvedValue({ dependencias: [] });
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('est-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.getEstructuraOrganica.mockRejectedValue(new Error('e'));
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('nueva dependencia raíz', async () => {
    api.crearDependencia.mockResolvedValue({ id: 'd3' });
    const user = userEvent.setup();
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('est-nueva'));
    fireEvent.change(screen.getByTestId('est-form-codigo'), { target: { value: 'D02' } });
    fireEvent.change(screen.getByTestId('est-form-nombre'), { target: { value: 'Jurídica' } });
    await user.click(screen.getByTestId('est-form-submit'));
    await waitFor(() => expect(api.crearDependencia).toHaveBeenCalled());
  });

  it('editar pre-llena', async () => {
    const user = userEvent.setup();
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('est-nodo'));
    await user.click(screen.getByTestId('est-nodo-editar'));
    expect(screen.getByTestId('est-form-nombre').value).toBe('Despacho');
  });

  it('reubicar con motivo', async () => {
    api.reubicarDependencia.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('est-nodo'));
    await user.click(screen.getByTestId('est-nodo-reubicar'));
    fireEvent.change(screen.getByTestId('est-reubicar-padre'), { target: { value: 'parent-uuid' } });
    fireEvent.change(screen.getByLabelText(/Motivo de la reubicación/i), { target: { value: 'reorganización institucional' } });
    await user.click(screen.getByTestId('est-reubicar-submit'));
    await waitFor(() => expect(api.reubicarDependencia).toHaveBeenCalled());
  });

  it('inactivar con motivo', async () => {
    api.inactivarDependencia.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('est-nodo'));
    await user.click(screen.getByTestId('est-nodo-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'cierre por reorganización' } });
    await user.click(screen.getByTestId('est-inactivar-submit'));
    await waitFor(() => expect(api.inactivarDependencia).toHaveBeenCalled());
  });

  it('agregar hija usa padre_id', async () => {
    api.crearDependencia.mockResolvedValue({ id: 'd3' });
    const user = userEvent.setup();
    render(<AdminEstructura session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('est-nodo'));
    await user.click(screen.getByTestId('est-nodo-agregar'));
    fireEvent.change(screen.getByTestId('est-form-codigo'), { target: { value: 'D01.2' } });
    fireEvent.change(screen.getByTestId('est-form-nombre'), { target: { value: 'Compras' } });
    await user.click(screen.getByTestId('est-form-submit'));
    await waitFor(() => expect(api.crearDependencia).toHaveBeenCalled());
  });

  it('sin permiso oculta CTAs', async () => {
    render(<AdminEstructura session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('est-tree'));
    expect(screen.queryByTestId('est-nueva')).toBeNull();
    expect(screen.queryByTestId('est-nodo-editar')).toBeNull();
  });
});
