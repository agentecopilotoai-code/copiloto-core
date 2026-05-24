import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  generarResumenIA: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { ResumenDocumento } from './ResumenDocumento.jsx';

const RESUMEN = {
  modelo: 'gpt-4o-mini', tokens: 320,
  generado_en: '2026-05-23T10:00:00Z',
  resumen: 'Documento sobre contratación de servicios profesionales.',
  temas: ['contratación', 'servicios'],
  entidades: [
    { texto: 'Pedro Pérez', tipo: 'persona' },
    { texto: 'Ministerio X', tipo: 'organización' },
  ],
  disclaimer: 'Resumen automático — verifique antes de citar.',
};

beforeEach(() => vi.clearAllMocks());

describe('ResumenDocumento', () => {
  it('renderiza CTA inicial sin resultado', () => {
    render(<ResumenDocumento session={{ token: 't' }} documentoId="d1" />);
    expect(screen.getByTestId('ia-resumen-pedir')).toBeInTheDocument();
    expect(screen.queryByTestId('ia-resumen-resultado')).toBeNull();
  });

  it('genera resumen y muestra resultado + temas + entidades', async () => {
    api.generarResumenIA.mockResolvedValue(RESUMEN);
    const user = userEvent.setup();
    render(<ResumenDocumento session={{ token: 't' }} documentoId="d1" />);
    await user.click(screen.getByTestId('ia-resumen-pedir'));
    await waitFor(() => expect(screen.getByTestId('ia-resumen-resultado')).toBeInTheDocument());
    expect(screen.getByTestId('ia-resumen-texto').textContent).toMatch(/Documento sobre/);
    expect(screen.getByTestId('ia-resumen-temas')).toBeInTheDocument();
    expect(screen.getByTestId('ia-resumen-entidades')).toBeInTheDocument();
  });

  it('cambiar longitud manda nuevo valor al regenerar', async () => {
    api.generarResumenIA.mockResolvedValue(RESUMEN);
    const user = userEvent.setup();
    render(<ResumenDocumento session={{ token: 't' }} documentoId="d1" />);
    fireEvent.change(screen.getByTestId('ia-resumen-len'), { target: { value: 'extenso' } });
    await user.click(screen.getByTestId('ia-resumen-pedir'));
    await waitFor(() => expect(api.generarResumenIA).toHaveBeenCalled());
    const payload = api.generarResumenIA.mock.calls[0][1];
    expect(payload.longitud).toBe('extenso');
  });

  it('error', async () => {
    api.generarResumenIA.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<ResumenDocumento session={{ token: 't' }} documentoId="d1" />);
    await user.click(screen.getByTestId('ia-resumen-pedir'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('autoGenerar genera al montar', async () => {
    api.generarResumenIA.mockResolvedValue(RESUMEN);
    render(<ResumenDocumento session={{ token: 't' }} documentoId="d1" autoGenerar />);
    await waitFor(() => expect(api.generarResumenIA).toHaveBeenCalled());
  });
});
