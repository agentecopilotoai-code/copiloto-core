import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  resumirDocumentoIa: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { ResumenAutomatico } from './ResumenAutomatico.jsx';

const RES = {
  resumen: 'Documento sobre licencias laborales 2025.',
  puntos_clave: ['vigencia 1 año', 'requiere firma'],
  entidades_extraidas: [{ tipo: 'fecha', valor: '2025-01-01' }],
  modelo: 'gpt-4', tokens: 320, coste_usd: 0.012,
};

beforeEach(() => vi.clearAllMocks());

describe('ResumenAutomatico', () => {
  it('sin permiso → no render', () => {
    const { container } = render(
      <ResumenAutomatico session={{}} roles={[]} entidadId="d1" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('generar muestra resumen + puntos + entidades + meta', async () => {
    api.resumirDocumentoIa.mockResolvedValue(RES);
    const user = userEvent.setup();
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.profesional']} entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-resumen-generar'));
    await waitFor(() => screen.getByTestId('ia-resumen-contenido'));
    expect(screen.getByTestId('ia-resumen-puntos').children).toHaveLength(2);
    expect(screen.getByTestId('ia-resumen-entidades')).toBeInTheDocument();
    expect(screen.getByTestId('ia-resumen-meta').textContent).toMatch(/gpt-4/);
  });

  it('error budget', async () => {
    const err = Object.assign(new Error('x'), { code: 'ia_budget_exceeded' });
    api.resumirDocumentoIa.mockRejectedValue(err);
    const user = userEvent.setup();
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.profesional']} entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-resumen-generar'));
    await waitFor(() => expect(screen.getByTestId('ia-resumen-error').textContent).toMatch(/Presupuesto/));
  });

  it('error genérico', async () => {
    api.resumirDocumentoIa.mockRejectedValue(new Error('falló'));
    const user = userEvent.setup();
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.profesional']} entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-resumen-generar'));
    await waitFor(() => expect(screen.getByTestId('ia-resumen-error').textContent).toMatch(/falló/));
  });

  it('cambio de idioma', async () => {
    api.resumirDocumentoIa.mockResolvedValue(RES);
    const user = userEvent.setup();
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.profesional']} entidadId="d1" />,
    );
    await user.selectOptions(screen.getByTestId('ia-resumen-idioma'), 'en');
    await user.click(screen.getByTestId('ia-resumen-generar'));
    await waitFor(() => screen.getByTestId('ia-resumen-contenido'));
    expect(api.resumirDocumentoIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ idioma: 'en' }),
    );
  });

  it('solo lectura (R) sin botón generar', () => {
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.usuario_consulta']} entidadId="d1" />,
    );
    expect(screen.queryByTestId('ia-resumen-generar')).toBeNull();
  });

  it('estado inicial sin resumen muestra mensaje muted', () => {
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.profesional']} entidadId="d1" />,
    );
    // El texto muted incluye "Pulse 'Generar resumen' para producir…".
    expect(screen.getByText(/Pulse/i)).toBeInTheDocument();
  });

  it('expediente como entidad', async () => {
    api.resumirDocumentoIa.mockResolvedValue({ ...RES, puntos_clave: [], entidades_extraidas: [] });
    const user = userEvent.setup();
    render(
      <ResumenAutomatico session={{ token: 't' }}
        roles={['gd.profesional']} entidadId="e1" entidad="expediente" />,
    );
    await user.click(screen.getByTestId('ia-resumen-generar'));
    await waitFor(() => screen.getByTestId('ia-resumen-contenido'));
    expect(screen.queryByTestId('ia-resumen-puntos')).toBeNull();
    expect(screen.queryByTestId('ia-resumen-entidades')).toBeNull();
  });
});
