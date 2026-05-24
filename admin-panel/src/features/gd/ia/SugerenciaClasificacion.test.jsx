import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  sugerirClasificacionIA: vi.fn(),
  feedbackSugerenciaClasificacionIA: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { SugerenciaClasificacion } from './SugerenciaClasificacion.jsx';

const SUG = {
  id: 's1', confianza: 0.92, modelo: 'gpt-4o-mini',
  serie: 'Contratos', serie_codigo: 'S001',
  subserie: 'Servicios', tipo_documental: 'Minuta',
  dependencia: 'Talento',
  razones: ['Detectó cláusulas contractuales', 'Mención a "contratista"'],
};

beforeEach(() => vi.clearAllMocks());

describe('SugerenciaClasificacion', () => {
  it('renderiza CTA inicial', () => {
    render(<SugerenciaClasificacion session={{ token: 't' }} contenido="texto" />);
    expect(screen.getByTestId('ia-sug-clas-pedir')).toBeInTheDocument();
  });

  it('pedir + mostrar resultado', async () => {
    api.sugerirClasificacionIA.mockResolvedValue(SUG);
    const user = userEvent.setup();
    render(<SugerenciaClasificacion session={{ token: 't' }} contenido="x" />);
    await user.click(screen.getByTestId('ia-sug-clas-pedir'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-clas-resultado')).toBeInTheDocument());
    expect(screen.getByTestId('ia-sug-conf').textContent).toMatch(/92/);
  });

  it('aceptar invoca onAceptar + feedback', async () => {
    api.sugerirClasificacionIA.mockResolvedValue(SUG);
    api.feedbackSugerenciaClasificacionIA.mockResolvedValue({ ok: true });
    const onAceptar = vi.fn();
    const user = userEvent.setup();
    render(<SugerenciaClasificacion session={{ token: 't' }} contenido="x" onAceptar={onAceptar} />);
    await user.click(screen.getByTestId('ia-sug-clas-pedir'));
    await waitFor(() => screen.getByTestId('ia-sug-aceptar'));
    await user.click(screen.getByTestId('ia-sug-aceptar'));
    expect(onAceptar).toHaveBeenCalledWith(SUG);
    await waitFor(() => expect(api.feedbackSugerenciaClasificacionIA).toHaveBeenCalled());
    expect(screen.getByTestId('ia-sug-feedback-ok')).toBeInTheDocument();
  });

  it('rechazar limpia + feedback', async () => {
    api.sugerirClasificacionIA.mockResolvedValue(SUG);
    api.feedbackSugerenciaClasificacionIA.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<SugerenciaClasificacion session={{ token: 't' }} contenido="x" />);
    await user.click(screen.getByTestId('ia-sug-clas-pedir'));
    await waitFor(() => screen.getByTestId('ia-sug-rechazar'));
    await user.click(screen.getByTestId('ia-sug-rechazar'));
    await waitFor(() => expect(api.feedbackSugerenciaClasificacionIA).toHaveBeenCalled());
  });

  it('error sugiriendo', async () => {
    api.sugerirClasificacionIA.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<SugerenciaClasificacion session={{ token: 't' }} contenido="x" />);
    await user.click(screen.getByTestId('ia-sug-clas-pedir'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('razones visibles en details', async () => {
    api.sugerirClasificacionIA.mockResolvedValue(SUG);
    const user = userEvent.setup();
    render(<SugerenciaClasificacion session={{ token: 't' }} contenido="x" />);
    await user.click(screen.getByTestId('ia-sug-clas-pedir'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-razones')).toBeInTheDocument());
  });
});
