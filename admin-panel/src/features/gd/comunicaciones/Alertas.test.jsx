import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listAlertas: vi.fn(),
  atenderAlerta: vi.fn(),
  listReglasAlerta: vi.fn(),
  crearReglaAlerta: vi.fn(),
  actualizarReglaAlerta: vi.fn(),
  inactivarReglaAlerta: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Alertas } from './Alertas.jsx';

const ROLES_USR = ['gd.jefe_dependencia'];
const ROLES_ADMIN = ['gd.admin_sistema', 'gd.jefe_dependencia'];

const A = {
  id: 'a1', tipo: 'pqrsd_vencimiento', severidad: 'alta',
  mensaje: 'PQRSD P-2026-001 vence en 24h', creada_en: '2026-05-23T10:00:00Z',
  estado: 'pendiente',
};
const R = {
  id: 'r1', nombre: 'PQRSD próxima a vencer',
  tipo: 'pqrsd_vencimiento', severidad: 'alta',
  umbral: 24, activa: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listAlertas.mockResolvedValue({ items: [A], total: 1 });
  api.listReglasAlerta.mockResolvedValue([R]);
});

describe('Alertas', () => {
  it('tabs y mis alertas por default', async () => {
    render(<Alertas session={{ token: 't' }} roles={ROLES_USR} />);
    expect(screen.getByTestId('alerta-tabs')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('alerta-table')).toBeInTheDocument());
  });

  it('sin permiso config no muestra tab Reglas', () => {
    render(<Alertas session={{ token: 't' }} roles={['gd.profesional']} />);
    expect(screen.queryByTestId('alerta-tab-btn-Reglas')).toBeNull();
  });

  it('empty', async () => {
    api.listAlertas.mockResolvedValue({ items: [], total: 0 });
    render(<Alertas session={{ token: 't' }} roles={ROLES_USR} />);
    await waitFor(() => expect(screen.getByTestId('alerta-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listAlertas.mockRejectedValue(new Error('e'));
    render(<Alertas session={{ token: 't' }} roles={ROLES_USR} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('filtros refetch', async () => {
    render(<Alertas session={{ token: 't' }} roles={ROLES_USR} />);
    await waitFor(() => expect(api.listAlertas).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('alerta-filter-tipo'), { target: { value: 'buzon_sobrecarga' } });
    fireEvent.change(screen.getByTestId('alerta-filter-sev'), { target: { value: 'alta' } });
    await waitFor(() => expect(api.listAlertas).toHaveBeenCalledTimes(3));
  });

  it('atender alerta con motivo', async () => {
    api.atenderAlerta.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Alertas session={{ token: 't' }} roles={ROLES_USR} />);
    await waitFor(() => screen.getByTestId('alerta-row'));
    await user.click(screen.getByTestId('alerta-atender'));
    fireEvent.change(screen.getByLabelText(/Acción tomada/i), { target: { value: 'reasignada a otra dependencia' } });
    await user.click(screen.getByTestId('alerta-atender-submit'));
    await waitFor(() => expect(api.atenderAlerta).toHaveBeenCalled());
  });

  it('tab Reglas: lista + nueva regla', async () => {
    api.crearReglaAlerta.mockResolvedValue({ id: 'r2' });
    const user = userEvent.setup();
    render(<Alertas session={{ token: 't' }} roles={ROLES_ADMIN} />);
    await user.click(screen.getByTestId('alerta-tab-btn-Reglas'));
    await waitFor(() => expect(screen.getByTestId('alerta-reglas-table')).toBeInTheDocument());
    await user.click(screen.getByTestId('alerta-regla-nueva'));
    fireEvent.change(screen.getByTestId('alerta-regla-nombre'), { target: { value: 'Nueva regla X' } });
    fireEvent.change(screen.getByTestId('alerta-regla-umbral'), { target: { value: '5' } });
    await user.click(screen.getByTestId('alerta-regla-submit'));
    await waitFor(() => expect(api.crearReglaAlerta).toHaveBeenCalled());
    const payload = api.crearReglaAlerta.mock.calls[0][1];
    expect(payload.umbral).toBe(5);
  });

  it('editar regla pre-llena', async () => {
    const user = userEvent.setup();
    render(<Alertas session={{ token: 't' }} roles={ROLES_ADMIN} />);
    await user.click(screen.getByTestId('alerta-tab-btn-Reglas'));
    await waitFor(() => screen.getByTestId('alerta-regla-row'));
    await user.click(screen.getByTestId('alerta-regla-editar'));
    expect(screen.getByTestId('alerta-regla-nombre').value).toBe('PQRSD próxima a vencer');
  });

  it('inactivar regla con motivo', async () => {
    api.inactivarReglaAlerta.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Alertas session={{ token: 't' }} roles={ROLES_ADMIN} />);
    await user.click(screen.getByTestId('alerta-tab-btn-Reglas'));
    await waitFor(() => screen.getByTestId('alerta-regla-row'));
    await user.click(screen.getByTestId('alerta-regla-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'regla obsoleta por cambio' } });
    await user.click(screen.getByTestId('alerta-regla-inact-submit'));
    await waitFor(() => expect(api.inactivarReglaAlerta).toHaveBeenCalled());
  });

  it('reglas empty', async () => {
    api.listReglasAlerta.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<Alertas session={{ token: 't' }} roles={ROLES_ADMIN} />);
    await user.click(screen.getByTestId('alerta-tab-btn-Reglas'));
    await waitFor(() => expect(screen.getByTestId('alerta-reglas-empty')).toBeInTheDocument());
  });

  it('reglas error', async () => {
    api.listReglasAlerta.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<Alertas session={{ token: 't' }} roles={ROLES_ADMIN} />);
    await user.click(screen.getByTestId('alerta-tab-btn-Reglas'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
