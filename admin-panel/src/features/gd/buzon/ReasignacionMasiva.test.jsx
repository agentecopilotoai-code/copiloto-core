import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getTareasPendientesUsuario: vi.fn(),
  reasignarTareasLote: vi.fn(),
  listUsuariosDependencia: vi.fn(),
}));
import {
  getTareasPendientesUsuario,
  reasignarTareasLote,
  listUsuariosDependencia,
} from '../services/gdApi.js';

import { ReasignacionMasiva } from './ReasignacionMasiva.jsx';

const TAREAS = [
  { id: 't1', titulo: 'PQRSD-2026-001', tipo: 'revision', vence_en: '2026-05-25T10:00:00Z',
    dependencia_id: 'd1', rol_compatible: 'gd.revisor' },
  { id: 't2', titulo: 'PQRSD-2026-002', tipo: 'aprobar', vence_en: '2026-05-26T10:00:00Z',
    dependencia_id: 'd1', rol_compatible: 'gd.jefe_dependencia' },
];

describe('ReasignacionMasiva', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listUsuariosDependencia.mockResolvedValue([
      { id: 'u-a', nombre: 'Ana', cargo: 'P' },
      { id: 'u-b', nombre: 'Beto', cargo: 'J' },
    ]);
  });

  it('empty cuando user no tiene pendientes', async () => {
    getTareasPendientesUsuario.mockResolvedValue({ items: [] });
    render(
      <ReasignacionMasiva session={{ token: 't' }} userId="u-x" />,
    );
    await waitFor(() => expect(screen.getByTestId('reasig-empty')).toBeInTheDocument());
  });

  it('error muestra alert', async () => {
    getTareasPendientesUsuario.mockRejectedValueOnce(new Error('e'));
    render(<ReasignacionMasiva session={{ token: 't' }} userId="u-x" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('lista tareas + pickers + submit deshabilitado hasta asignar todos', async () => {
    getTareasPendientesUsuario.mockResolvedValue({ items: TAREAS });
    render(<ReasignacionMasiva session={{ token: 't' }} userId="u-x" usuarioNombre="Pedro" />);
    await waitFor(() => expect(screen.getAllByTestId('reasig-row')).toHaveLength(2));
    expect(screen.getByTestId('reasig-submit')).toBeDisabled();
  });

  it('asignar todos los responsables + justificación habilita submit y dispara', async () => {
    getTareasPendientesUsuario.mockResolvedValue({ items: TAREAS });
    reasignarTareasLote.mockResolvedValueOnce({ reasignadas: 2 });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(
      <ReasignacionMasiva session={{ token: 't' }} userId="u-x" usuarioNombre="Pedro" onSuccess={onSuccess} />,
    );
    await waitFor(() => expect(screen.getAllByTestId('reasig-row')).toHaveLength(2));
    await waitFor(() => screen.getByTestId('reasig-picker-t1-select'));
    fireEvent.change(screen.getByTestId('reasig-picker-t1-select'), { target: { value: 'u-a' } });
    fireEvent.change(screen.getByTestId('reasig-picker-t2-select'), { target: { value: 'u-b' } });
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'Pedro inactivado por retiro' },
    });
    await waitFor(() => expect(screen.getByTestId('reasig-submit')).not.toBeDisabled());
    await user.click(screen.getByTestId('reasig-submit'));
    await waitFor(() => expect(reasignarTareasLote).toHaveBeenCalled());
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
  });

  it('botón Cancelar dispara onCancel', async () => {
    getTareasPendientesUsuario.mockResolvedValue({ items: TAREAS });
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <ReasignacionMasiva session={{ token: 't' }} userId="u-x" onCancel={onCancel} />,
    );
    await waitFor(() => screen.getAllByTestId('reasig-row'));
    await user.click(screen.getByTestId('reasig-cancelar'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('error al submit muestra alert', async () => {
    getTareasPendientesUsuario.mockResolvedValue({ items: [TAREAS[0]] });
    reasignarTareasLote.mockRejectedValueOnce(new Error('cuota'));
    const user = userEvent.setup();
    render(<ReasignacionMasiva session={{ token: 't' }} userId="u-x" />);
    await waitFor(() => screen.getByTestId('reasig-picker-t1-select'));
    fireEvent.change(screen.getByTestId('reasig-picker-t1-select'), { target: { value: 'u-a' } });
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'OK porque sí debe ser largo' },
    });
    await user.click(screen.getByTestId('reasig-submit'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
