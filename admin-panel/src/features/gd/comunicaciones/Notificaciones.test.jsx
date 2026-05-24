import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listMisNotificaciones: vi.fn(),
  marcarNotificacionLeida: vi.fn(),
  marcarTodasNotificacionesLeidas: vi.fn(),
  getPreferenciasNotificaciones: vi.fn(),
  actualizarPreferenciasNotificaciones: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Notificaciones } from './Notificaciones.jsx';

const N = {
  id: 'n1', titulo: 'PQRSD asignada', mensaje: 'Le asignaron una PQRSD',
  creada_en: '2026-05-23T10:00:00Z', leida: false, enlace: '/gd/pqrsd/p1',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listMisNotificaciones.mockResolvedValue({ items: [N], total: 1, no_leidas: 1 });
  api.getPreferenciasNotificaciones.mockResolvedValue({
    preferencias: { radicado_asignado: { email: true } },
  });
});

describe('Notificaciones', () => {
  it('renderiza tabs y bandeja por default', async () => {
    render(<Notificaciones session={{ token: 't' }} />);
    expect(screen.getByTestId('not-tabs')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('not-bandeja')).toBeInTheDocument());
  });

  it('item no leído resaltado + badge no_leidas', async () => {
    render(<Notificaciones session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('not-item')).toBeInTheDocument());
    expect(screen.getByTestId('not-badge-no-leidas').textContent).toMatch(/1/);
  });

  it('empty', async () => {
    api.listMisNotificaciones.mockResolvedValue({ items: [], total: 0, no_leidas: 0 });
    render(<Notificaciones session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('not-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listMisNotificaciones.mockRejectedValue(new Error('e'));
    render(<Notificaciones session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('click item marca leído + navega', async () => {
    api.marcarNotificacionLeida.mockResolvedValue({ ok: true });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<Notificaciones session={{ token: 't' }} onNavigate={onNavigate} />);
    await user.click(await screen.findByTestId('not-item'));
    await waitFor(() => expect(api.marcarNotificacionLeida).toHaveBeenCalled());
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/p1');
  });

  it('marcar todas leídas', async () => {
    api.marcarTodasNotificacionesLeidas.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Notificaciones session={{ token: 't' }} />);
    await user.click(await screen.findByTestId('not-marcar-todas'));
    await waitFor(() => expect(api.marcarTodasNotificacionesLeidas).toHaveBeenCalled());
  });

  it('checkbox solo no leídas refetch', async () => {
    render(<Notificaciones session={{ token: 't' }} />);
    await waitFor(() => expect(api.listMisNotificaciones).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId('not-solo-no-leidas'));
    await waitFor(() => expect(api.listMisNotificaciones).toHaveBeenCalledTimes(2));
  });

  it('tab Preferencias renderiza tabla + guardar', async () => {
    api.actualizarPreferenciasNotificaciones.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<Notificaciones session={{ token: 't' }} />);
    await user.click(screen.getByTestId('not-tab-btn-Preferencias'));
    await waitFor(() => expect(screen.getByTestId('not-prefs-table')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('not-prefs-radicado_asignado-sms'));
    await user.click(screen.getByTestId('not-prefs-guardar'));
    await waitFor(() => expect(api.actualizarPreferenciasNotificaciones).toHaveBeenCalled());
  });

  it('preferencias error al guardar', async () => {
    api.actualizarPreferenciasNotificaciones.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Notificaciones session={{ token: 't' }} />);
    await user.click(screen.getByTestId('not-tab-btn-Preferencias'));
    await waitFor(() => screen.getByTestId('not-prefs-table'));
    await user.click(screen.getByTestId('not-prefs-guardar'));
    await waitFor(() => expect(screen.getByTestId('not-prefs-info').textContent).toMatch(/boom/));
  });

  it('preferencias error de carga', async () => {
    api.getPreferenciasNotificaciones.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<Notificaciones session={{ token: 't' }} />);
    await user.click(screen.getByTestId('not-tab-btn-Preferencias'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
