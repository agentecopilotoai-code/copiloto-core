import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listPerifericos: vi.fn(),
  listTrabajosImpresion: vi.fn(),
  imprimirEtiqueta: vi.fn(),
  imprimirConstancia: vi.fn(),
  reimprimir: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Impresion } from './Impresion.jsx';

const ROLES = ['gd.radicador', 'gd.coordinador_vu'];

const IMPRESORA = {
  id: 'imp1', codigo: 'IMP-01', tipo: 'impresora', modelo: 'HP',
  ubicacion: 'V.U.', en_linea: true,
};
const T = {
  id: 'trabajo-abcdef', tipo: 'etiqueta', numero_radicado: '2026-E-100',
  periferico_codigo: 'IMP-01', estado: 'completado',
  creado_en: '2026-05-23T10:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listPerifericos.mockResolvedValue({ items: [IMPRESORA] });
  api.listTrabajosImpresion.mockResolvedValue({ items: [T] });
});

describe('Impresion', () => {
  it('sin permiso muestra warning', () => {
    render(<Impresion session={{ token: 't' }} roles={['gd.firmante']} />);
    expect(screen.getByTestId('imp-no-perm')).toBeInTheDocument();
  });

  it('renderiza tabs y form Imprimir por default', async () => {
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('imp-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('imp-form')).toBeInTheDocument();
  });

  it('imprimir etiqueta OK', async () => {
    api.imprimirEtiqueta.mockResolvedValue({ trabajo_id: 'trab1' });
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('imp-radicado'), { target: { value: '2026-E-100' } });
    await waitFor(() => screen.getByTestId('imp-impresora'));
    fireEvent.change(screen.getByTestId('imp-impresora'), { target: { value: 'imp1' } });
    await user.click(screen.getByTestId('imp-submit'));
    await waitFor(() => expect(api.imprimirEtiqueta).toHaveBeenCalled());
  });

  it('cambiar tipo a constancia y imprimir', async () => {
    api.imprimirConstancia.mockResolvedValue({ trabajo_id: 'trab2' });
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('imp-tipo'), { target: { value: 'constancia' } });
    fireEvent.change(screen.getByTestId('imp-radicado'), { target: { value: 'r1' } });
    await waitFor(() => screen.getByTestId('imp-impresora'));
    fireEvent.change(screen.getByTestId('imp-impresora'), { target: { value: 'imp1' } });
    await user.click(screen.getByTestId('imp-submit'));
    await waitFor(() => expect(api.imprimirConstancia).toHaveBeenCalled());
  });

  it('imprimir error', async () => {
    api.imprimirEtiqueta.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    fireEvent.change(screen.getByTestId('imp-radicado'), { target: { value: 'r1' } });
    await waitFor(() => screen.getByTestId('imp-impresora'));
    fireEvent.change(screen.getByTestId('imp-impresora'), { target: { value: 'imp1' } });
    await user.click(screen.getByTestId('imp-submit'));
    await waitFor(() => expect(screen.getByTestId('imp-info').textContent).toMatch(/boom/));
  });

  it('tab Cola muestra tabla', async () => {
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('imp-tab-btn-Cola'));
    await waitFor(() => expect(screen.getByTestId('imp-cola-table')).toBeInTheDocument());
  });

  it('cola empty', async () => {
    api.listTrabajosImpresion.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('imp-tab-btn-Cola'));
    await waitFor(() => expect(screen.getByTestId('imp-cola-empty')).toBeInTheDocument());
  });

  it('cola error', async () => {
    api.listTrabajosImpresion.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('imp-tab-btn-Cola'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('reimprimir con motivo', async () => {
    api.reimprimir.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('imp-tab-btn-Cola'));
    await waitFor(() => screen.getByTestId('imp-reimprimir'));
    await user.click(screen.getByTestId('imp-reimprimir'));
    fireEvent.change(screen.getByLabelText(/Motivo de reimpresión/i), { target: { value: 'etiqueta dañada por humedad' } });
    await user.click(screen.getByTestId('imp-reimp-submit'));
    await waitFor(() => expect(api.reimprimir).toHaveBeenCalled());
  });

  it('sin permiso reimprimir oculta CTA', async () => {
    const user = userEvent.setup();
    render(<Impresion session={{ token: 't' }} roles={['gd.radicador']} />);
    await user.click(screen.getByTestId('imp-tab-btn-Cola'));
    await waitFor(() => screen.getByTestId('imp-cola-table'));
    expect(screen.queryByTestId('imp-reimprimir')).toBeNull();
  });
});
