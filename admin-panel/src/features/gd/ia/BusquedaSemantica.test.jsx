import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  buscarSemanticoIA: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { BusquedaSemantica } from './BusquedaSemantica.jsx';

const ROLES = ['gd.profesional'];

beforeEach(() => vi.clearAllMocks());

describe('BusquedaSemantica', () => {
  it('sin permiso muestra warning', () => {
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.firmante']} />);
    expect(screen.getByTestId('iabs-no-perm')).toBeInTheDocument();
  });

  it('form se renderiza', () => {
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('iabs-form')).toBeInTheDocument();
  });

  it('búsqueda + resultados', async () => {
    api.buscarSemanticoIA.mockResolvedValue({
      items: [{ id: 'd1', titulo: 'X', tipo: 'oficio', score: 0.92, fragmento: 'cita' }],
    });
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('iabs-q'), { target: { value: 'contratos' } });
    await user.click(screen.getByTestId('iabs-submit'));
    await waitFor(() => expect(screen.getByTestId('iabs-resultados')).toBeInTheDocument());
    expect(screen.getByTestId('iabs-fragmento')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.buscarSemanticoIA.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('iabs-q'), { target: { value: 'xyz' } });
    await user.click(screen.getByTestId('iabs-submit'));
    await waitFor(() => expect(screen.getByTestId('iabs-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.buscarSemanticoIA.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('iabs-q'), { target: { value: 'x' } });
    await user.click(screen.getByTestId('iabs-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('cambio de scope se incluye en payload', async () => {
    api.buscarSemanticoIA.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('iabs-q'), { target: { value: 'x' } });
    fireEvent.change(screen.getByTestId('iabs-scope'), { target: { value: 'mi_dependencia' } });
    await user.click(screen.getByTestId('iabs-submit'));
    await waitFor(() => expect(api.buscarSemanticoIA).toHaveBeenCalled());
    const payload = api.buscarSemanticoIA.mock.calls[0][1];
    expect(payload.scope).toBe('mi_dependencia');
  });

  it('row click navega', async () => {
    api.buscarSemanticoIA.mockResolvedValue({
      items: [{ id: 'd1', titulo: 'X', tipo: 'oficio', score: 0.5 }],
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} onNavigate={onNavigate} />);
    fireEvent.change(screen.getByTestId('iabs-q'), { target: { value: 'x' } });
    await user.click(screen.getByTestId('iabs-submit'));
    await waitFor(() => screen.getByTestId('iabs-resultado'));
    await user.click(screen.getByTestId('iabs-resultado'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d1');
  });

  it('submit deshabilitado sin query', () => {
    render(<BusquedaSemantica session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('iabs-submit')).toBeDisabled();
  });
});
