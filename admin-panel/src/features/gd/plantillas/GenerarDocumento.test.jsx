import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getPlantilla: vi.fn(),
  generarDocumentoDePlantilla: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { GenerarDocumento } from './GenerarDocumento.jsx';

const ROLES = ['gd.profesional'];

const PLT = {
  id: 'p1', nombre: 'Oficio', version_actual: 1,
  cuerpo: 'Para {{destino}}, asunto: {{asunto}}.',
  variables: [
    { nombre: 'destino', tipo: 'texto', descripcion: 'Destinatario' },
    { nombre: 'asunto', tipo: 'texto_largo', descripcion: 'Asunto', requerida: true },
  ],
};

describe('GenerarDocumento', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPlantilla.mockResolvedValue(PLT);
  });

  it('renderiza form de variables + preview', async () => {
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('gen-layout')).toBeInTheDocument());
    expect(screen.getByTestId('gen-vars-form')).toBeInTheDocument();
    expect(screen.getByTestId('gen-preview')).toBeInTheDocument();
  });

  it('preview se actualiza al cambiar variables', async () => {
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('gen-vars-form'));
    fireEvent.change(screen.getByTestId('gen-var-destino'), { target: { value: 'Alcaldía' } });
    expect(screen.getByTestId('gen-preview').textContent).toMatch(/Alcaldía/);
  });

  it('submit deshabilitado mientras hay variables requeridas vacías', async () => {
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('gen-vars-form'));
    expect(screen.getByTestId('gen-submit')).toBeDisabled();
  });

  it('submit OK navega a documento generado', async () => {
    api.generarDocumentoDePlantilla.mockResolvedValue({ id: 'd99' });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('gen-vars-form'));
    fireEvent.change(screen.getByTestId('gen-var-destino'), { target: { value: 'X' } });
    fireEvent.change(screen.getByTestId('gen-var-asunto'), { target: { value: 'Y' } });
    await user.click(screen.getByTestId('gen-submit'));
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d99'));
  });

  it('submit error muestra alert', async () => {
    api.generarDocumentoDePlantilla.mockRejectedValue(new Error('falla'));
    const user = userEvent.setup();
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('gen-vars-form'));
    fireEvent.change(screen.getByTestId('gen-var-destino'), { target: { value: 'X' } });
    fireEvent.change(screen.getByTestId('gen-var-asunto'), { target: { value: 'Y' } });
    await user.click(screen.getByTestId('gen-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/falla/));
  });

  it('sin permiso muestra warning', async () => {
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={['gd.usuario_consulta']} />);
    await waitFor(() => expect(screen.getByTestId('gen-no-perm')).toBeInTheDocument());
  });

  it('sin variables muestra mensaje', async () => {
    api.getPlantilla.mockResolvedValue({ ...PLT, variables: [] });
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('gen-sin-vars')).toBeInTheDocument());
  });

  it('cancelar navega a listado', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('gen-vars-form'));
    await user.click(screen.getByTestId('gen-cancel'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/plantillas');
  });

  it('error al cargar plantilla', async () => {
    api.getPlantilla.mockRejectedValue(new Error('e'));
    render(<GenerarDocumento session={{ token: 't' }} plantillaId="p1" roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
