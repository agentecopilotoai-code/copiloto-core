import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getTarea: vi.fn(),
  ejecutarAccionTarea: vi.fn(),
  listUsuariosDependencia: vi.fn(),
  listAuditoria: vi.fn(),
}));
import {
  getTarea, ejecutarAccionTarea,
  listUsuariosDependencia, listAuditoria,
} from '../services/gdApi.js';

import { TareaFicha } from './TareaFicha.jsx';

const TAREA = {
  id: 't1',
  titulo: 'Revisar PQRSD #2026-005',
  tipo: 'revision',
  estado: 'asignada',
  responsable_nombre: 'Juan',
  responsable_user_id: 'u-juan',
  dependencia_id: 'd1',
  rol_compatible: 'gd.revisor',
  asignada_en: '2026-05-22T10:00:00Z',
  vence_en: '2026-05-25T10:00:00Z',
  descripcion: 'Revisar respuesta antes de aprobar',
  acciones_permitidas: ['iniciar', 'devolver', 'finalizar', 'reasignar', 'escalar'],
  entidad_relacionada: { tipo: 'pqrsd', ruta: '/gd/pqrsd/p5' },
};

describe('TareaFicha', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getTarea.mockResolvedValue(TAREA);
    listAuditoria.mockResolvedValue({ items: [] });
    listUsuariosDependencia.mockResolvedValue([
      { id: 'u-ana', nombre: 'Ana M', cargo: 'Profesional' },
    ]);
  });

  it('carga tarea + muestra estado + acciones', async () => {
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => expect(screen.getAllByText('Revisar PQRSD #2026-005').length).toBeGreaterThanOrEqual(1));
    expect(screen.getByTestId('tarea-actions')).toBeInTheDocument();
    expect(screen.getByTestId('btn-iniciar')).toBeInTheDocument();
    expect(screen.getByTestId('btn-finalizar')).toBeInTheDocument();
  });

  it('error muestra alert', async () => {
    getTarea.mockRejectedValueOnce(new Error('404'));
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('botón Iniciar ejecuta sin justificación', async () => {
    ejecutarAccionTarea.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => screen.getByTestId('btn-iniciar'));
    await user.click(screen.getByTestId('btn-iniciar'));
    await user.click(screen.getByTestId('tarea-modal-confirm'));
    await waitFor(() => expect(ejecutarAccionTarea).toHaveBeenCalledWith(
      { token: 't' }, 't1', 'iniciar', { justificacion: undefined, nuevo_responsable_user_id: undefined },
    ));
  });

  it('botón Devolver requiere justificación', async () => {
    ejecutarAccionTarea.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => screen.getByTestId('btn-devolver'));
    await user.click(screen.getByTestId('btn-devolver'));
    expect(screen.getByTestId('tarea-modal-confirm')).toBeDisabled();
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'Falta documento de soporte' },
    });
    await user.click(screen.getByTestId('tarea-modal-confirm'));
    await waitFor(() => expect(ejecutarAccionTarea).toHaveBeenCalled());
  });

  it('Reasignar requiere picker + justificación', async () => {
    ejecutarAccionTarea.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => screen.getByTestId('btn-reasignar'));
    await user.click(screen.getByTestId('btn-reasignar'));
    // Esperar a que cargue lista usuarios
    await waitFor(() => screen.getByTestId('modal-usuario-picker-select'));
    fireEvent.change(screen.getByTestId('modal-usuario-picker-select'), { target: { value: 'u-ana' } });
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'María entra en vacaciones' },
    });
    await user.click(screen.getByTestId('tarea-modal-confirm'));
    await waitFor(() => expect(ejecutarAccionTarea).toHaveBeenCalledWith(
      { token: 't' }, 't1', 'reasignar',
      expect.objectContaining({ nuevo_responsable_user_id: 'u-ana' }),
    ));
  });

  it('botón Abrir entidad relacionada navega', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('abrir-entidad'));
    await user.click(screen.getByTestId('abrir-entidad'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/p5');
  });

  it('cancelar modal cierra sin enviar', async () => {
    const user = userEvent.setup();
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => screen.getByTestId('btn-iniciar'));
    await user.click(screen.getByTestId('btn-iniciar'));
    await user.click(screen.getByText('Cancelar'));
    expect(screen.queryByTestId('tarea-modal')).toBeNull();
  });

  it('botón Escalar es danger tone + requiere justificación', async () => {
    const user = userEvent.setup();
    render(<TareaFicha session={{ token: 't' }} tareaId="t1" />);
    await waitFor(() => screen.getByTestId('btn-escalar'));
    await user.click(screen.getByTestId('btn-escalar'));
    expect(screen.getByTestId('tarea-modal-confirm')).toBeDisabled();
  });
});
