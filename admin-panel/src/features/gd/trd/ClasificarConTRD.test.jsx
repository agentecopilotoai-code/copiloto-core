import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listTRD: vi.fn(),
  clasificarConTRD: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { ClasificarConTRD } from './ClasificarConTRD.jsx';

const SERIES = [{
  id: 's1', codigo: 'S001', nombre: 'Contratos',
  subseries: [{
    id: 'ss1', codigo: 'S001.1', nombre: 'Servicios',
    tipos: [{ id: 't1', nombre: 'Minuta' }],
  }],
}];

describe('ClasificarConTRD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listTRD.mockResolvedValue({ items: SERIES });
  });

  it('renderiza form con select de serie', async () => {
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => expect(screen.getByTestId('clasificar-form')).toBeInTheDocument());
    expect(screen.getByTestId('clasificar-serie')).toBeInTheDocument();
  });

  it('selecciona serie y muestra subseries', async () => {
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('clasificar-serie'));
    fireEvent.change(screen.getByTestId('clasificar-serie'), { target: { value: 's1' } });
    await waitFor(() => expect(screen.getByTestId('clasificar-subserie')).toBeInTheDocument());
  });

  it('selecciona subserie y muestra tipos', async () => {
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('clasificar-serie'));
    fireEvent.change(screen.getByTestId('clasificar-serie'), { target: { value: 's1' } });
    fireEvent.change(screen.getByTestId('clasificar-subserie'), { target: { value: 'ss1' } });
    await waitFor(() => expect(screen.getByTestId('clasificar-tipo')).toBeInTheDocument());
  });

  it('submit OK invoca clasificar con payload', async () => {
    api.clasificarConTRD.mockResolvedValue({ id: 'c1' });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" onSuccess={onSuccess} />);
    await waitFor(() => screen.getByTestId('clasificar-serie'));
    fireEvent.change(screen.getByTestId('clasificar-serie'), { target: { value: 's1' } });
    fireEvent.change(screen.getByLabelText(/Observaciones/i), { target: { value: 'clasificación inicial documento contrato' } });
    await user.click(screen.getByTestId('clasificar-submit'));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    const payload = api.clasificarConTRD.mock.calls[0][1];
    expect(payload.serie_id).toBe('s1');
    expect(payload.documento_id).toBe('d1');
  });

  it('submit error muestra alert', async () => {
    api.clasificarConTRD.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('clasificar-serie'));
    fireEvent.change(screen.getByTestId('clasificar-serie'), { target: { value: 's1' } });
    fireEvent.change(screen.getByLabelText(/Observaciones/i), { target: { value: 'obs válida documento' } });
    await user.click(screen.getByTestId('clasificar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('cancelar invoca onCancel', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<ClasificarConTRD session={{ token: 't' }} expedienteId="e1" onCancel={onCancel} />);
    await waitFor(() => screen.getByTestId('clasificar-serie'));
    await user.click(screen.getByTestId('clasificar-cancel'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('error al cargar TRD', async () => {
    api.listTRD.mockRejectedValue(new Error('e'));
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('submit deshabilitado sin serie', async () => {
    render(<ClasificarConTRD session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('clasificar-submit'));
    expect(screen.getByTestId('clasificar-submit')).toBeDisabled();
  });
});
