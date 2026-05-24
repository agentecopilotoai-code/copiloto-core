import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPlantillas: vi.fn(),
  getPlantilla: vi.fn(),
  crearPlantilla: vi.fn(),
  actualizarPlantilla: vi.fn(),
  nuevaVersionPlantilla: vi.fn(),
  inactivarPlantilla: vi.fn(),
  generarDocumentoDePlantilla: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminPlantillas } from './AdminPlantillas.jsx';

const ROLES = ['gd.admin_plantillas'];

const P1 = {
  id: 'p1', nombre: 'Oficio estándar', tipo: 'oficio',
  version_actual: 2, activa: true, descripcion: 'd',
  cuerpo: 'Cuerpo {{nombre}}',
  variables: [{ nombre: 'nombre', tipo: 'texto', descripcion: 'Nombre destinatario' }],
};

describe('AdminPlantillas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listPlantillas.mockResolvedValue({ items: [P1], total: 1 });
    api.getPlantilla.mockResolvedValue(P1);
  });

  it('renderiza layout con lista', async () => {
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('plt-layout')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('plt-row')).toBeInTheDocument());
  });

  it('empty', async () => {
    api.listPlantillas.mockResolvedValue({ items: [], total: 0 });
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('plt-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listPlantillas.mockRejectedValue(new Error('e'));
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('click en row muestra detalle', async () => {
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('plt-row'));
    await user.click(screen.getByTestId('plt-row'));
    await waitFor(() => expect(screen.getByTestId('plt-detalle')).toBeInTheDocument());
    expect(screen.getByTestId('plt-variables')).toBeInTheDocument();
  });

  it('botón Nueva (con permiso) abre form', async () => {
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('plt-new'));
    expect(screen.getByTestId('plt-form')).toBeInTheDocument();
  });

  it('crear plantilla submit OK', async () => {
    api.crearPlantilla.mockResolvedValue({ id: 'p2' });
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('plt-new'));
    fireEvent.change(screen.getByTestId('plt-form-nombre'), { target: { value: 'Acta' } });
    fireEvent.change(screen.getByTestId('plt-form-tipo'), { target: { value: 'acta' } });
    fireEvent.change(screen.getByTestId('plt-form-cuerpo'), { target: { value: 'Cuerpo' } });
    await user.click(screen.getByTestId('plt-form-submit'));
    await waitFor(() => expect(api.crearPlantilla).toHaveBeenCalled());
  });

  it('crear submit error muestra alert', async () => {
    api.crearPlantilla.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('plt-new'));
    fireEvent.change(screen.getByTestId('plt-form-nombre'), { target: { value: 'Acta' } });
    await user.click(screen.getByTestId('plt-form-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('botón Editar carga form con datos', async () => {
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('plt-row'));
    await user.click(await screen.findByTestId('plt-edit'));
    await waitFor(() => expect(screen.getByTestId('plt-form-nombre').value).toBe('Oficio estándar'));
  });

  it('Nueva versión submit OK', async () => {
    api.nuevaVersionPlantilla.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('plt-row'));
    await user.click(await screen.findByTestId('plt-nueva-version'));
    fireEvent.change(screen.getByTestId('plt-nuevaver-cuerpo'), { target: { value: 'Nuevo cuerpo' } });
    fireEvent.change(screen.getByLabelText(/Motivo de la nueva versión/i), { target: { value: 'corrige texto institucional' } });
    await user.click(screen.getByTestId('plt-nuevaver-submit'));
    await waitFor(() => expect(api.nuevaVersionPlantilla).toHaveBeenCalled());
  });

  it('Inactivar submit OK', async () => {
    api.inactivarPlantilla.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminPlantillas session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('plt-row'));
    await user.click(await screen.findByTestId('plt-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'deprecada por normativa' } });
    await user.click(screen.getByTestId('plt-inactivar-submit'));
    await waitFor(() => expect(api.inactivarPlantilla).toHaveBeenCalled());
  });

  it('botón Generar navega (requiere PLA-USE además de PLA-001)', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    // admin_plantillas (PLA-001 RW) + profesional (PLA-USE R) — combinación
    // que se da en jefes de dependencia que también administran plantillas.
    render(
      <AdminPlantillas
        session={{ token: 't' }}
        roles={['gd.admin_plantillas', 'gd.profesional']}
        onNavigate={onNavigate}
      />,
    );
    await user.click(await screen.findByTestId('plt-row'));
    await user.click(await screen.findByTestId('plt-generar'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/plantillas/p1/generar');
  });
});
