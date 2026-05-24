import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  enviarMensajeAsistenteIA: vi.fn(),
  listConversacionesAsistente: vi.fn(),
  getConversacionAsistente: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Asistente } from './Asistente.jsx';

const ROLES = ['gd.profesional'];

beforeEach(() => {
  vi.clearAllMocks();
  api.listConversacionesAsistente.mockResolvedValue([]);
});

describe('Asistente', () => {
  it('sin permiso muestra warning', () => {
    render(<Asistente session={{ token: 't' }} roles={['gd.firmante']} />);
    expect(screen.getByTestId('ia-asis-no-perm')).toBeInTheDocument();
  });

  it('layout vacío inicial', async () => {
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('ia-asis-layout')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('ia-asis-vacio')).toBeInTheDocument());
    expect(screen.getByTestId('ia-asis-empty-convs')).toBeInTheDocument();
  });

  it('enviar mensaje crea conversación nueva', async () => {
    api.enviarMensajeAsistenteIA.mockResolvedValue({
      conversacion_id: 'c1',
      mensaje: { id: 'm1', rol: 'asistente', contenido: 'Respuesta' },
    });
    api.getConversacionAsistente.mockResolvedValue({
      id: 'c1', mensajes: [
        { id: 'u1', rol: 'usuario', contenido: 'Hola' },
        { id: 'm1', rol: 'asistente', contenido: 'Respuesta' },
      ],
    });
    api.listConversacionesAsistente.mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ id: 'c1', titulo: 'Hola' }]);
    const user = userEvent.setup();
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('ia-asis-input'), { target: { value: 'Hola' } });
    await user.click(screen.getByTestId('ia-asis-enviar'));
    await waitFor(() => expect(api.enviarMensajeAsistenteIA).toHaveBeenCalled());
    await waitFor(() => expect(api.getConversacionAsistente).toHaveBeenCalledWith({ token: 't' }, 'c1'));
  });

  it('lista conversaciones se renderiza', async () => {
    api.listConversacionesAsistente.mockResolvedValue([
      { id: 'c1', titulo: 'Cons 1', actualizada_en: '2026-05-20T10:00:00Z' },
      { id: 'c2', titulo: 'Cons 2', actualizada_en: '2026-05-22T10:00:00Z' },
    ]);
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getAllByTestId('ia-asis-conv-row')).toHaveLength(2));
  });

  it('seleccionar conversación carga mensajes', async () => {
    api.listConversacionesAsistente.mockResolvedValue([
      { id: 'c1', titulo: 'Cons 1' },
    ]);
    api.getConversacionAsistente.mockResolvedValue({
      id: 'c1', mensajes: [
        { id: 'u1', rol: 'usuario', contenido: 'Hola' },
        { id: 'm1', rol: 'asistente', contenido: 'Respuesta',
          citas: [{ titulo: 'Doc 1', entidad: 'documento', entidad_id: 'd1' }] },
      ],
    });
    const user = userEvent.setup();
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('ia-asis-conv-row'));
    await waitFor(() => expect(screen.getAllByTestId('ia-asis-msg')).toHaveLength(2));
    expect(screen.getByTestId('ia-asis-citas')).toBeInTheDocument();
  });

  it('error al enviar muestra alert', async () => {
    api.enviarMensajeAsistenteIA.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('ia-asis-input'), { target: { value: 'x' } });
    await user.click(screen.getByTestId('ia-asis-enviar'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('error cargando lista de conversaciones', async () => {
    api.listConversacionesAsistente.mockRejectedValue(new Error('e'));
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('nueva conversación resetea estado', async () => {
    api.listConversacionesAsistente.mockResolvedValue([{ id: 'c1', titulo: 'X' }]);
    const user = userEvent.setup();
    render(<Asistente session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('ia-asis-nueva'));
    expect(screen.getByTestId('ia-asis-input').value).toBe('');
  });
});
