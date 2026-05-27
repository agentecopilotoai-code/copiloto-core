import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  preguntarAsistenteIa: vi.fn(),
  listConversacionesIa: vi.fn(),
  getConversacionIa: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { AsistenteConversacional } from './AsistenteConversacional.jsx';

beforeEach(() => {
  vi.clearAllMocks();
  api.listConversacionesIa.mockResolvedValue({
    items: [{ id: 'c1', titulo: 'PQRSD junio', mensajes_count: 4, tokens_total: 1200 }],
    total: 1,
  });
});

describe('AsistenteConversacional', () => {
  it('sin permiso muestra aviso', () => {
    render(<AsistenteConversacional session={{}} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('ia-asis-no-perm')).toBeInTheDocument();
  });

  it('renderiza historial y chat vacío', async () => {
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    await waitFor(() => screen.getByTestId('ia-asis-historial'));
    expect(screen.getByTestId('ia-asis-chat')).toBeInTheDocument();
  });

  it('envía mensaje y muestra respuesta con citas', async () => {
    api.preguntarAsistenteIa.mockResolvedValue({
      conversacion_id: 'c-new',
      respuesta: 'Hay 3 PQRSD abiertas.',
      citas: [{ documento_id: 'd1', titulo: 'reporte', fragmento: '3 abiertas' }],
    });
    const user = userEvent.setup();
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-asis-input'), '¿cuántas pqrsd abiertas?');
    await user.click(screen.getByTestId('ia-asis-enviar'));
    await waitFor(() => expect(screen.getByTestId('ia-asis-msg-user')).toBeInTheDocument());
    await waitFor(() => screen.getByTestId('ia-asis-msg-assistant'));
    // El summary tiene texto "1 cita" — específico para distinguir
    // de "Sin conversaciones".
    const summary = screen.getByText(/^\d+ citas?$/);
    await user.click(summary);
    expect(screen.getByTestId('ia-asis-citas')).toBeInTheDocument();
  });

  it('botón nueva conversación resetea', async () => {
    api.preguntarAsistenteIa.mockResolvedValue({
      conversacion_id: 'c-new', respuesta: 'ok', citas: [],
    });
    const user = userEvent.setup();
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-asis-input'), 'hola');
    await user.click(screen.getByTestId('ia-asis-enviar'));
    await waitFor(() => screen.getByTestId('ia-asis-msg-user'));
    await user.click(screen.getByTestId('ia-asis-nueva'));
    expect(screen.queryByTestId('ia-asis-msg-user')).toBeNull();
  });

  it('navega a documento citado', async () => {
    api.preguntarAsistenteIa.mockResolvedValue({
      conversacion_id: 'c1',
      respuesta: 'según el doc d9',
      citas: [{ documento_id: 'd9', titulo: 'doc 9' }],
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']}
        onNavigate={onNavigate} />,
    );
    await user.type(screen.getByTestId('ia-asis-input'), '¿qué dice doc 9?');
    await user.click(screen.getByTestId('ia-asis-enviar'));
    await waitFor(() => screen.getByTestId('ia-asis-msg-assistant'));
    const det = screen.getByText(/^\d+ citas?$/);
    await user.click(det);
    await user.click(screen.getByText('doc 9'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d9');
  });

  it('error backend', async () => {
    api.preguntarAsistenteIa.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-asis-input'), 'x');
    await user.click(screen.getByTestId('ia-asis-enviar'));
    await waitFor(() => screen.getByTestId('ia-asis-error'));
  });

  it('click en una conversación del historial', async () => {
    api.getConversacionIa.mockResolvedValue({
      id: 'c1', titulo: 'PQRSD junio',
      mensajes: [{ rol: 'user', contenido: 'hola' }],
    });
    const user = userEvent.setup();
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    await waitFor(() => screen.getByTestId('ia-asis-conv-item'));
    await user.click(screen.getByTestId('ia-asis-conv-item'));
    await waitFor(() => expect(api.getConversacionIa).toHaveBeenCalled());
  });

  it('historial vacío muestra mensaje', async () => {
    api.listConversacionesIa.mockResolvedValue({ items: [], total: 0 });
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    await waitFor(() => expect(screen.getByText(/Sin conversaciones/)).toBeInTheDocument());
  });

  it('input vacío deshabilita enviar', () => {
    render(<AsistenteConversacional session={{ token: 't' }} roles={['gd.profesional']} />);
    expect(screen.getByTestId('ia-asis-enviar')).toBeDisabled();
  });
});
