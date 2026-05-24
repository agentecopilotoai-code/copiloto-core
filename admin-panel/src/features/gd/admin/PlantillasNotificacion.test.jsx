import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPlantillasNotificacion: vi.fn(),
  actualizarPlantillaNotificacion: vi.fn(),
  probarPlantillaNotificacion: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { PlantillasNotificacion } from './PlantillasNotificacion.jsx';

const ROLES = ['gd.admin_sistema'];
const PLT = {
  codigo: 'pqrsd-asignada', nombre: 'PQRSD asignada', canal: 'email',
  asunto: 'Tiene una PQRSD asignada', cuerpo: 'Hola {{nombre}}',
  variables: ['nombre', 'numero_radicado'], version_actual: 2,
};

describe('PlantillasNotificacion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listPlantillasNotificacion.mockResolvedValue([PLT]);
  });

  it('renderiza layout', async () => {
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('not-layout')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('not-row')).toBeInTheDocument());
  });

  it('empty', async () => {
    api.listPlantillasNotificacion.mockResolvedValue([]);
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('not-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listPlantillasNotificacion.mockRejectedValue(new Error('e'));
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('seleccionar muestra editor', async () => {
    const user = userEvent.setup();
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('not-row'));
    expect(screen.getByTestId('not-editor')).toBeInTheDocument();
    expect(screen.getByTestId('not-asunto').value).toBe('Tiene una PQRSD asignada');
  });

  it('guardar plantilla', async () => {
    api.actualizarPlantillaNotificacion.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('not-row'));
    fireEvent.change(screen.getByTestId('not-cuerpo'), { target: { value: 'Cambio' } });
    await user.click(screen.getByTestId('not-guardar'));
    await waitFor(() => expect(api.actualizarPlantillaNotificacion).toHaveBeenCalled());
  });

  it('probar envío OK', async () => {
    api.probarPlantillaNotificacion.mockResolvedValue({ message_id: 'm1' });
    const user = userEvent.setup();
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('not-row'));
    fireEvent.change(screen.getByTestId('not-prueba-dest'), { target: { value: 'a@b.co' } });
    await user.click(screen.getByTestId('not-probar'));
    await waitFor(() => expect(screen.getByTestId('not-prueba-info').textContent).toMatch(/encolado/));
  });

  it('probar error', async () => {
    api.probarPlantillaNotificacion.mockRejectedValue(new Error('smtp down'));
    const user = userEvent.setup();
    render(<PlantillasNotificacion session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('not-row'));
    fireEvent.change(screen.getByTestId('not-prueba-dest'), { target: { value: 'a@b.co' } });
    await user.click(screen.getByTestId('not-probar'));
    await waitFor(() => expect(screen.getByTestId('not-prueba-info').textContent).toMatch(/smtp down/));
  });

  it('sin permiso muestra preview', async () => {
    const user = userEvent.setup();
    render(<PlantillasNotificacion session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await user.click(await screen.findByTestId('not-row'));
    expect(screen.getByTestId('not-preview')).toBeInTheDocument();
  });
});
