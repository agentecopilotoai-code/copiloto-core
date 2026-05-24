import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPerifericos: vi.fn(),
  listColaDigitalizacion: vi.fn(),
  digitalizarIndividual: vi.fn(),
  digitalizarLote: vi.fn(),
  asociarDigitalizacionARadicado: vi.fn(),
  reemplazarDigitalizacion: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Digitalizacion } from './Digitalizacion.jsx';

const ROLES_OP = ['gd.radicador'];                     // PER-006/007
const ROLES_COORD = ['gd.coordinador_vu'];            // PER-008/009
const ROLES_ALL = ['gd.radicador', 'gd.coordinador_vu'];

const ESCANER = {
  id: 'esc1', codigo: 'ESC-01', tipo: 'escaner', modelo: 'Fujitsu',
  ubicacion: 'V.U.', en_linea: true,
};
const T = {
  id: 'tabcdef', tipo: 'individual', cantidad: 1,
  periferico_codigo: 'ESC-01', estado: 'completado',
  creado_en: '2026-05-23T10:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listPerifericos.mockResolvedValue({ items: [ESCANER] });
  api.listColaDigitalizacion.mockResolvedValue({ items: [T] });
});

describe('Digitalizacion', () => {
  it('sin permiso muestra warning', () => {
    render(<Digitalizacion session={{ token: 't' }} roles={['gd.firmante']} />);
    expect(screen.getByTestId('dig-no-perm')).toBeInTheDocument();
  });

  it('renderiza tabs y form Individual por default', async () => {
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_OP} />);
    expect(screen.getByTestId('dig-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('dig-ind-form')).toBeInTheDocument();
  });

  it('individual OK', async () => {
    api.digitalizarIndividual.mockResolvedValue({ id: 'd1' });
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_OP} />);
    await waitFor(() => screen.getByTestId('dig-ind-escaner'));
    fireEvent.change(screen.getByTestId('dig-ind-escaner'), { target: { value: 'esc1' } });
    fireEvent.change(screen.getByTestId('dig-ind-radicado'), { target: { value: '2026-E-100' } });
    fireEvent.change(screen.getByTestId('dig-ind-dpi'), { target: { value: '600' } });
    fireEvent.change(screen.getByTestId('dig-ind-color'), { target: { value: 'color' } });
    fireEvent.change(screen.getByTestId('dig-ind-formato'), { target: { value: 'tiff' } });
    await user.click(screen.getByTestId('dig-ind-submit'));
    await waitFor(() => expect(api.digitalizarIndividual).toHaveBeenCalled());
    const payload = api.digitalizarIndividual.mock.calls[0][1];
    expect(payload.dpi).toBe(600);
    expect(payload.formato).toBe('tiff');
  });

  it('individual error', async () => {
    api.digitalizarIndividual.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_OP} />);
    await waitFor(() => screen.getByTestId('dig-ind-escaner'));
    fireEvent.change(screen.getByTestId('dig-ind-escaner'), { target: { value: 'esc1' } });
    fireEvent.change(screen.getByTestId('dig-ind-radicado'), { target: { value: 'r1' } });
    await user.click(screen.getByTestId('dig-ind-submit'));
    await waitFor(() => expect(screen.getByTestId('dig-ind-info').textContent).toMatch(/boom/));
  });

  it('tab Lote: detección de cantidad + submit', async () => {
    api.digitalizarLote.mockResolvedValue({ id: 'l1' });
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_OP} />);
    await user.click(screen.getByTestId('dig-tab-btn-Lote'));
    await waitFor(() => screen.getByTestId('dig-lote-escaner'));
    fireEvent.change(screen.getByTestId('dig-lote-escaner'), { target: { value: 'esc1' } });
    fireEvent.change(screen.getByTestId('dig-lote-radicados'), {
      target: { value: '2026-E-100, 2026-E-101\n2026-E-102' },
    });
    expect(screen.getByTestId('dig-lote-count').textContent).toMatch(/3/);
    await user.click(screen.getByTestId('dig-lote-submit'));
    await waitFor(() => expect(api.digitalizarLote).toHaveBeenCalled());
    const payload = api.digitalizarLote.mock.calls[0][1];
    expect(payload.radicados_ids).toHaveLength(3);
  });

  it('lote cola muestra tabla', async () => {
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_OP} />);
    await user.click(screen.getByTestId('dig-tab-btn-Lote'));
    await waitFor(() => expect(screen.getByTestId('dig-cola-table')).toBeInTheDocument());
  });

  it('cola empty', async () => {
    api.listColaDigitalizacion.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_OP} />);
    await user.click(screen.getByTestId('dig-tab-btn-Lote'));
    await waitFor(() => expect(screen.getByTestId('dig-cola-empty')).toBeInTheDocument());
  });

  it('lote sin permiso PER-007', async () => {
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_COORD} />);
    await user.click(screen.getByTestId('dig-tab-btn-Lote'));
    // ROL coordinador_vu sí tiene PER-007 (en VU group). Verifico que SÍ aparece el form.
    expect(screen.getByTestId('dig-lote-form')).toBeInTheDocument();
  });

  it('tab Asociar requiere PER-008/009', async () => {
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_COORD} />);
    await user.click(screen.getByTestId('dig-tab-btn-Asociar / reemplazar'));
    expect(screen.getByTestId('dig-asoc-panel')).toBeInTheDocument();
  });

  it('asociar a radicado con motivo', async () => {
    api.asociarDigitalizacionARadicado.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_ALL} />);
    await user.click(screen.getByTestId('dig-tab-btn-Asociar / reemplazar'));
    fireEvent.change(screen.getByTestId('dig-asoc-dig'), { target: { value: 'dig-uuid' } });
    fireEvent.change(screen.getByTestId('dig-asoc-radicado'), { target: { value: '2026-E-100' } });
    fireEvent.change(screen.getByLabelText(/Motivo de la asociación/i), { target: { value: 'digitalización previa al radicado cerrado' } });
    await user.click(screen.getByTestId('dig-asoc-submit'));
    await waitFor(() => expect(api.asociarDigitalizacionARadicado).toHaveBeenCalled());
  });

  it('reemplazar digitalización con motivo', async () => {
    api.reemplazarDigitalizacion.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_ALL} />);
    await user.click(screen.getByTestId('dig-tab-btn-Asociar / reemplazar'));
    fireEvent.change(screen.getByTestId('dig-reemp-dig'), { target: { value: 'dig-uuid' } });
    fireEvent.change(screen.getByTestId('dig-reemp-arch'), { target: { value: 'arch-uuid' } });
    fireEvent.change(screen.getByLabelText(/Motivo del reemplazo/i), { target: { value: 'digitalización dañada por humedad' } });
    await user.click(screen.getByTestId('dig-reemp-submit'));
    await waitFor(() => expect(api.reemplazarDigitalizacion).toHaveBeenCalled());
  });

  it('asociar error muestra alert', async () => {
    api.asociarDigitalizacionARadicado.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Digitalizacion session={{ token: 't' }} roles={ROLES_COORD} />);
    await user.click(screen.getByTestId('dig-tab-btn-Asociar / reemplazar'));
    fireEvent.change(screen.getByTestId('dig-asoc-dig'), { target: { value: 'd' } });
    fireEvent.change(screen.getByTestId('dig-asoc-radicado'), { target: { value: 'r' } });
    fireEvent.change(screen.getByLabelText(/Motivo de la asociación/i), { target: { value: 'motivo válido suficiente' } });
    await user.click(screen.getByTestId('dig-asoc-submit'));
    await waitFor(() => expect(screen.getByTestId('dig-asoc-info').textContent).toMatch(/boom/));
  });
});
