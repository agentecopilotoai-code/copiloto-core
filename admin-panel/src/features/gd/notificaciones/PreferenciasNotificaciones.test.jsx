import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getPreferenciasNotif: vi.fn(),
  actualizarPreferenciasNotif: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { PreferenciasNotificaciones } from './PreferenciasNotificaciones.jsx';

const PREFS = {
  canales: { in_app: true, email: true, push: false, sms: false },
  por_tipo: {
    'pqrsd_nueva': { in_app: true, email: true, push: false, sms: false },
    'vencimiento': { in_app: true, email: false, push: true, sms: false },
  },
  no_molestar: { inicio: '22:00', fin: '06:00' },
};

const ROLES = ['gd.profesional'];

beforeEach(() => {
  vi.clearAllMocks();
  api.getPreferenciasNotif.mockResolvedValue(PREFS);
});

describe('PreferenciasNotificaciones', () => {
  it('renderiza canales globales', async () => {
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-canales'));
    expect(screen.getByTestId('not-pref-canal-email')).toBeChecked();
    expect(screen.getByTestId('not-pref-canal-sms')).not.toBeChecked();
  });

  it('renderiza tipos', async () => {
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-tipos'));
    expect(screen.getAllByTestId('not-pref-tipo-row')).toHaveLength(2);
  });

  it('toggle email global + guardar', async () => {
    api.actualizarPreferenciasNotif.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-canal-email'));
    await user.click(screen.getByTestId('not-pref-canal-email'));
    await user.click(screen.getByTestId('not-pref-guardar'));
    await waitFor(() => expect(api.actualizarPreferenciasNotif).toHaveBeenCalled());
    const payload = api.actualizarPreferenciasNotif.mock.calls[0][1];
    expect(payload.canales.email).toBe(false);
  });

  it('toggle por tipo', async () => {
    api.actualizarPreferenciasNotif.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-tipo-pqrsd_nueva-sms'));
    await user.click(screen.getByTestId('not-pref-tipo-pqrsd_nueva-sms'));
    await user.click(screen.getByTestId('not-pref-guardar'));
    await waitFor(() => expect(api.actualizarPreferenciasNotif).toHaveBeenCalled());
    const payload = api.actualizarPreferenciasNotif.mock.calls[0][1];
    expect(payload.por_tipo.pqrsd_nueva.sms).toBe(true);
  });

  it('no molestar: cambia hora inicio', async () => {
    api.actualizarPreferenciasNotif.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-nm-inicio'));
    fireEvent.change(screen.getByTestId('not-pref-nm-inicio'), { target: { value: '23:00' } });
    await user.click(screen.getByTestId('not-pref-guardar'));
    const payload = api.actualizarPreferenciasNotif.mock.calls[0][1];
    expect(payload.no_molestar.inicio).toBe('23:00');
  });

  it('no molestar: quitar', async () => {
    api.actualizarPreferenciasNotif.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-nm-clear'));
    await user.click(screen.getByTestId('not-pref-nm-clear'));
    await user.click(screen.getByTestId('not-pref-guardar'));
    const payload = api.actualizarPreferenciasNotif.mock.calls[0][1];
    expect(payload.no_molestar).toBeNull();
  });

  it('error al guardar', async () => {
    api.actualizarPreferenciasNotif.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-guardar'));
    await user.click(screen.getByTestId('not-pref-guardar'));
    await waitFor(() => expect(screen.getByTestId('not-pref-feedback').textContent).toMatch(/boom/));
  });

  it('error de carga', async () => {
    api.getPreferenciasNotif.mockRejectedValue(new Error('e'));
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-error'));
  });

  it('sin permiso NOT-PREF RW', () => {
    // Todos los roles GD tienen NOT-PREF (any/all), pero podemos
    // pasar roles vacío para forzar el aviso.
    render(<PreferenciasNotificaciones session={{}} roles={[]} />);
    expect(screen.getByTestId('not-pref-no-perm')).toBeInTheDocument();
  });

  it('sin por_tipo no renderiza tabla', async () => {
    api.getPreferenciasNotif.mockResolvedValue({
      canales: { in_app: true, email: false },
      por_tipo: {},
    });
    render(<PreferenciasNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-pref-canales'));
    expect(screen.queryByTestId('not-pref-tipos')).toBeNull();
  });
});
