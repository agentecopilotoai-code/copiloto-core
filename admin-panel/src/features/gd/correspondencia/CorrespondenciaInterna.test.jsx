import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listCorrespondencia: vi.fn(),
  crearCorrespondenciaInterna: vi.fn(),
}));
import {
  listCorrespondencia,
  crearCorrespondenciaInterna,
} from '../services/gdApi.js';

import { CorrespondenciaInterna } from './CorrespondenciaInterna.jsx';

const ITEM = {
  id: 'c1', asunto: 'Solicitud', remitente_dependencia_nombre: 'Talento',
  destinatario_dependencia_nombre: 'Jurídica', fecha: '2026-05-23T10:00:00Z',
  estado: 'enviada', leida: false,
};

describe('CorrespondenciaInterna', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listCorrespondencia.mockResolvedValue({ items: [ITEM], total: 1 });
  });

  it('renderiza tabs y por default Recibidas con tabla', async () => {
    render(<CorrespondenciaInterna session={{ token: 't' }} />);
    expect(screen.getByTestId('ci-tabs')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('ci-table')).toBeInTheDocument());
  });

  it('cambio a tab Enviadas dispara nuevo fetch con bandeja=enviadas', async () => {
    const user = userEvent.setup();
    render(<CorrespondenciaInterna session={{ token: 't' }} />);
    await waitFor(() => expect(listCorrespondencia).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('ci-tab-btn-Enviadas'));
    await waitFor(() => expect(listCorrespondencia).toHaveBeenCalledTimes(2));
    const args = listCorrespondencia.mock.calls.at(-1)[1];
    expect(args.bandeja).toBe('enviadas');
  });

  it('empty bandeja', async () => {
    listCorrespondencia.mockResolvedValue({ items: [], total: 0 });
    render(<CorrespondenciaInterna session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('ci-empty')).toBeInTheDocument());
  });

  it('error muestra alert', async () => {
    listCorrespondencia.mockRejectedValue(new Error('e'));
    render(<CorrespondenciaInterna session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('click en row navega a ficha', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<CorrespondenciaInterna session={{ token: 't' }} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('ci-row'));
    await user.click(screen.getByTestId('ci-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/correspondencia/c1');
  });

  it('tab Nueva muestra form + submit OK navega a Enviadas', async () => {
    crearCorrespondenciaInterna.mockResolvedValueOnce({ id: 'new1' });
    const user = userEvent.setup();
    render(<CorrespondenciaInterna session={{ token: 't' }} dependencias={[{ id: 'd1', nombre: 'Talento' }]} />);
    await user.click(screen.getByTestId('ci-tab-btn-Nueva'));
    expect(screen.getByTestId('ci-nueva-form')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('ci-asunto'), { target: { value: 'Hola' } });
    fireEvent.change(screen.getByTestId('ci-dep-destino'), { target: { value: 'd1' } });
    await user.click(screen.getByTestId('ci-enviar'));
    await waitFor(() => expect(crearCorrespondenciaInterna).toHaveBeenCalled());
  });

  it('submit con error muestra alert', async () => {
    crearCorrespondenciaInterna.mockRejectedValueOnce(new Error('falla'));
    const user = userEvent.setup();
    render(<CorrespondenciaInterna session={{ token: 't' }} dependencias={[{ id: 'd1', nombre: 'X' }]} />);
    await user.click(screen.getByTestId('ci-tab-btn-Nueva'));
    fireEvent.change(screen.getByTestId('ci-asunto'), { target: { value: 'AB' } });
    fireEvent.change(screen.getByTestId('ci-dep-destino'), { target: { value: 'd1' } });
    await user.click(screen.getByTestId('ci-enviar'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('refresh dispara fetch adicional', async () => {
    const user = userEvent.setup();
    render(<CorrespondenciaInterna session={{ token: 't' }} />);
    await waitFor(() => screen.getByTestId('ci-table'));
    await user.click(screen.getByTestId('ci-refresh'));
    expect(listCorrespondencia).toHaveBeenCalledTimes(2);
  });
});
