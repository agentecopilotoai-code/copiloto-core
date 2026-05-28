import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listConfigCanalesEmail: vi.fn(),
  actualizarConfigCanalEmail: vi.fn(),
  probarCanalEmail: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { ConfigCanalesEmail } from './ConfigCanalesEmail.jsx';

const CANALES = {
  items: [
    { id: 'c1', nombre: 'SMTP corp', tipo: 'SMTP',
      host: 'smtp.org', port: 587, usuario: 'noreply',
      tls: true, activo: true, ultimo_check: '2026-05-27T10:00:00Z' },
    { id: 'c2', nombre: 'IMAP entrada', tipo: 'IMAP',
      host: 'imap.org', port: 993, usuario: 'ventanilla',
      tls: true, activo: false },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listConfigCanalesEmail.mockResolvedValue(CANALES);
});

describe('ConfigCanalesEmail', () => {
  it('sin permiso → aviso', () => {
    api.listConfigCanalesEmail.mockResolvedValue({ items: [] });
    render(<ConfigCanalesEmail session={{}} roles={['gd.profesional']} />);
    expect(screen.getByTestId('cor-cfg-no-perm')).toBeInTheDocument();
  });

  it('admin sistema ve canales', async () => {
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => expect(screen.getAllByTestId('cor-cfg-canal')).toHaveLength(2));
  });

  it('toggle activo + guardar', async () => {
    api.actualizarConfigCanalEmail.mockResolvedValue({ id: 'c1' });
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-activo-c1'));
    await user.click(screen.getByTestId('cor-cfg-activo-c1'));
    await user.click(screen.getByTestId('cor-cfg-guardar-c1'));
    await waitFor(() => expect(api.actualizarConfigCanalEmail).toHaveBeenCalled());
    await waitFor(() => screen.getByTestId('cor-cfg-feedback-c1'));
  });

  it('cambia host + port (port via fireEvent)', async () => {
    api.actualizarConfigCanalEmail.mockResolvedValue({ id: 'c1' });
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-host-c1'));
    await user.clear(screen.getByTestId('cor-cfg-host-c1'));
    await user.type(screen.getByTestId('cor-cfg-host-c1'), 'newsmtp.org');
    fireEvent.change(screen.getByTestId('cor-cfg-port-c1'), { target: { value: '465' } });
    await user.click(screen.getByTestId('cor-cfg-guardar-c1'));
    await waitFor(() => expect(api.actualizarConfigCanalEmail).toHaveBeenCalledWith(
      expect.anything(), 'c1',
      expect.objectContaining({ host: 'newsmtp.org', port: 465 }),
    ));
  });

  it('cambio de password se incluye', async () => {
    api.actualizarConfigCanalEmail.mockResolvedValue({ id: 'c1' });
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-pwd-c1'));
    await user.type(screen.getByTestId('cor-cfg-pwd-c1'), 'newpass123');
    await user.click(screen.getByTestId('cor-cfg-guardar-c1'));
    await waitFor(() => expect(api.actualizarConfigCanalEmail).toHaveBeenCalledWith(
      expect.anything(), 'c1',
      expect.objectContaining({ password: 'newpass123' }),
    ));
  });

  it('password vacío NO se envía', async () => {
    api.actualizarConfigCanalEmail.mockResolvedValue({ id: 'c1' });
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-guardar-c1'));
    await user.click(screen.getByTestId('cor-cfg-guardar-c1'));
    await waitFor(() => expect(api.actualizarConfigCanalEmail).toHaveBeenCalled());
    const payload = api.actualizarConfigCanalEmail.mock.calls[0][2];
    expect(payload.password).toBeUndefined();
  });

  it('probar conexión ok', async () => {
    api.probarCanalEmail.mockResolvedValue({ ok: true, latencia_ms: 120 });
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-probar-c1'));
    await user.click(screen.getByTestId('cor-cfg-probar-c1'));
    await waitFor(() => expect(screen.getByTestId('cor-cfg-prueba-c1').textContent).toMatch(/120 ms/));
  });

  it('probar conexión falla', async () => {
    api.probarCanalEmail.mockRejectedValue(new Error('timeout'));
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-probar-c1'));
    await user.click(screen.getByTestId('cor-cfg-probar-c1'));
    await waitFor(() => expect(screen.getByTestId('cor-cfg-prueba-c1').textContent).toMatch(/timeout/));
  });

  it('error guardando', async () => {
    api.actualizarConfigCanalEmail.mockRejectedValue(new Error('falló'));
    const user = userEvent.setup();
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-guardar-c1'));
    await user.click(screen.getByTestId('cor-cfg-guardar-c1'));
    await waitFor(() => expect(screen.getByTestId('cor-cfg-feedback-c1').textContent).toMatch(/falló/));
  });

  it('error cargando', async () => {
    api.listConfigCanalesEmail.mockRejectedValue(new Error('e'));
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-error'));
  });

  it('empty', async () => {
    api.listConfigCanalesEmail.mockResolvedValue({ items: [] });
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-cfg-empty'));
  });

  it('admin_seguridad solo R', async () => {
    render(<ConfigCanalesEmail session={{ token: 't' }} roles={['gd.admin_seguridad']} />);
    await waitFor(() => screen.getAllByTestId('cor-cfg-canal'));
    expect(screen.queryByTestId('cor-cfg-guardar-c1')).toBeNull();
  });
});
