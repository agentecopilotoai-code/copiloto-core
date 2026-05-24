import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  crearRadicadoEntrada: vi.fn(),
}));
import { crearRadicadoEntrada } from '../services/gdApi.js';

import { NuevoRadicadoEntrada } from './NuevoRadicadoEntrada.jsx';

const CANALES = [
  { id: 'c1', nombre: 'Web' },
  { id: 'c2', nombre: 'Presencial' },
];

const TERCERO_RES = [
  {
    id: 't1', nombre_completo: 'Juan Pérez',
    tipo_doc_identidad: 'CC', numero_doc_identidad: '79.123.456',
    correo_electronico: 'juan@x.co',
  },
];

describe('NuevoRadicadoEntrada — wizard', () => {
  beforeEach(() => vi.clearAllMocks());

  function setup(props = {}) {
    return render(
      <NuevoRadicadoEntrada
        session={{ token: 't' }}
        canales={CANALES}
        {...props}
      />,
    );
  }

  it('paso 1: stepper + canal disabled hasta seleccionar', () => {
    setup();
    expect(screen.getByTestId('stepper-bar')).toBeInTheDocument();
    expect(screen.getByTestId('wizard-next')).toBeDisabled();
    expect(screen.getByTestId('wizard-prev')).toBeDisabled();
  });

  it('paso 1: seleccionar canal + tercero + avanzar a paso 2', async () => {
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Juan');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    expect(screen.getByTestId('wizard-next')).not.toBeDisabled();
    await user.click(screen.getByTestId('wizard-next'));
    expect(screen.getByTestId('nuevo-radicado-step').getAttribute('data-step')).toBe('2');
  });

  it('crear tercero inline + dispara onTerceroCrear', async () => {
    const onTerceroCrear = vi.fn().mockResolvedValue({ id: 't-new' });
    const user = userEvent.setup();
    setup({ onTerceroCrear });
    await user.click(screen.getByTestId('tercero-crear-toggle'));
    expect(screen.getByTestId('tercero-inline-form')).toBeInTheDocument();
    await user.type(screen.getByTestId('tercero-numero'), '12345');
    await user.type(screen.getByTestId('tercero-nombre'), 'Ana');
    await user.click(screen.getByTestId('tercero-crear-submit'));
    await waitFor(() => expect(onTerceroCrear).toHaveBeenCalled());
  });

  it('busqueda de 1 char no dispara onTerceroSearch', async () => {
    const onTerceroSearch = vi.fn();
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    await user.type(screen.getByTestId('tercero-search'), 'J');
    expect(onTerceroSearch).not.toHaveBeenCalled();
  });

  it('paso 2: asunto + descripción + sugerencia IA aceptar', async () => {
    const onSugerenciaIa = vi.fn().mockResolvedValue({
      id: 'sug1', resumen: 'Resumen IA',
    });
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onSugerenciaIa, onTerceroSearch });
    // Paso 1 → 2
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Juan');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next'));

    // Paso 2
    await user.type(screen.getByTestId('asunto-input'), 'Solicitud');
    await user.click(screen.getByTestId('ia-pedir'));
    await waitFor(() => expect(onSugerenciaIa).toHaveBeenCalled());
    await user.click(screen.getByTestId('ia-aceptar'));
    expect(screen.getByTestId('descripcion-input').value).toContain('Resumen IA');
  });

  it('paso 2: IA rechazar limpia sugerencia', async () => {
    const onSugerenciaIa = vi.fn().mockResolvedValue({ id: 's1', resumen: 'R' });
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onSugerenciaIa, onTerceroSearch });
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'J');
    fireEvent.change(screen.getByTestId('tercero-search'), { target: { value: 'Ju' } });
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next'));
    await user.type(screen.getByTestId('asunto-input'), 'X');
    await user.click(screen.getByTestId('ia-pedir'));
    await waitFor(() => screen.getByTestId('ia-aceptar'));
    await user.click(screen.getByTestId('ia-rechazar'));
    expect(screen.getByTestId('ia-pedir')).toBeInTheDocument();
  });

  it('paso 3: drop file actualiza anexos', async () => {
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    // ir a paso 3 directo (simulate)
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Ju');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next')); // step 2
    await user.type(screen.getByTestId('asunto-input'), 'Hola');
    await user.click(screen.getByTestId('wizard-next')); // step 3
    expect(screen.getByTestId('anexos-dropzone')).toBeInTheDocument();
    // simular file via input
    const file = new File(['hello'], 'test.pdf', { type: 'application/pdf' });
    const input = screen.getByTestId('anexos-file-input');
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByTestId('anexo-item')).toBeInTheDocument();
  });

  it('archivo con extensión no aceptada se ignora', async () => {
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Ju');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next'));
    await user.type(screen.getByTestId('asunto-input'), 'Hola');
    await user.click(screen.getByTestId('wizard-next'));
    const file = new File(['x'], 'malware.exe', { type: 'application/x-msdownload' });
    fireEvent.change(screen.getByTestId('anexos-file-input'), { target: { files: [file] } });
    expect(screen.queryByTestId('anexo-item')).toBeNull();
  });

  it('paso 4: seleccionar tipo + submit dispara crearRadicadoEntrada', async () => {
    crearRadicadoEntrada.mockResolvedValueOnce({
      id: 'r-new', numero_radicado: '2026-E-001',
      codigo_verificacion: 'XYZ', fecha_radicacion: '2026-05-23T10:00:00Z',
      asunto: 'Hola',
    });
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Ju');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next'));
    await user.type(screen.getByTestId('asunto-input'), 'Hola');
    await user.click(screen.getByTestId('wizard-next'));
    await user.click(screen.getByTestId('wizard-next')); // step 4
    fireEvent.change(screen.getByTestId('tipo-clasificacion-select'), { target: { value: 'pqrsd' } });
    await user.click(screen.getByTestId('wizard-submit'));
    await waitFor(() => expect(crearRadicadoEntrada).toHaveBeenCalled());
  });

  it('error del backend se muestra como alert', async () => {
    crearRadicadoEntrada.mockRejectedValueOnce({
      body: { detail: { message: 'duplicado' } },
    });
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Ju');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next'));
    await user.type(screen.getByTestId('asunto-input'), 'Hola');
    await user.click(screen.getByTestId('wizard-next'));
    await user.click(screen.getByTestId('wizard-next'));
    fireEvent.change(screen.getByTestId('tipo-clasificacion-select'), { target: { value: 'pqrsd' } });
    await user.click(screen.getByTestId('wizard-submit'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText(/duplicado/)).toBeInTheDocument();
  });

  it('botón Anterior decrementa step', async () => {
    const onTerceroSearch = vi.fn().mockResolvedValue(TERCERO_RES);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    fireEvent.change(screen.getByTestId('canal-select'), { target: { value: 'c1' } });
    await user.type(screen.getByTestId('tercero-search'), 'Ju');
    await waitFor(() => screen.getByTestId('tercero-results'));
    await user.click(screen.getByText('Juan Pérez'));
    await user.click(screen.getByTestId('wizard-next'));
    await user.click(screen.getByTestId('wizard-prev'));
    expect(screen.getByTestId('nuevo-radicado-step').getAttribute('data-step')).toBe('1');
  });

  it('busqueda de terceros sin resultados no rompe', async () => {
    const onTerceroSearch = vi.fn().mockResolvedValue([]);
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    await user.type(screen.getByTestId('tercero-search'), 'XYZ');
    await waitFor(() => expect(onTerceroSearch).toHaveBeenCalled());
    expect(screen.queryByTestId('tercero-results')).toBeNull();
  });

  it('onTerceroSearch rechaza → silencioso (no throw)', async () => {
    const onTerceroSearch = vi.fn().mockRejectedValue(new Error('net'));
    const user = userEvent.setup();
    setup({ onTerceroSearch });
    await user.type(screen.getByTestId('tercero-search'), 'XYZ');
    await waitFor(() => expect(onTerceroSearch).toHaveBeenCalled());
    expect(screen.queryByTestId('tercero-results')).toBeNull();
  });
});
