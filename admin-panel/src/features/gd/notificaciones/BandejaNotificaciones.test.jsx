import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listNotificacionesInbox: vi.fn(),
  marcarNotifLeida: vi.fn(),
  marcarNotifsTodasLeidas: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { BandejaNotificaciones } from './BandejaNotificaciones.jsx';

const ROLES = ['gd.profesional'];

const NOTIFS = {
  items: [
    { id: 'n1', titulo: 'PQRSD nueva', mensaje: 'Tienes una PQRSD nueva',
      tipo: 'informativa', severidad: 'media', leida: false,
      link: '/gd/pqrsd/123', creado_en: '2026-05-27T10:00:00Z' },
    { id: 'n2', titulo: 'Doc firmado', mensaje: 'Documento firmado',
      tipo: 'sistema', leida: true, creado_en: '2026-05-27T09:00:00Z' },
  ],
  total: 2, no_leidas: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listNotificacionesInbox.mockResolvedValue(NOTIFS);
});

describe('BandejaNotificaciones', () => {
  it('lista items + badge no leídas', async () => {
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getAllByTestId('not-bd-item')).toHaveLength(2));
    expect(screen.getByTestId('not-bd-badge-noleidas').textContent).toMatch(/1/);
  });

  it('click marca leída y navega', async () => {
    api.marcarNotifLeida.mockResolvedValue({});
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES}
      onNavigate={onNavigate} />);
    await waitFor(() => screen.getAllByTestId('not-bd-item'));
    await user.click(screen.getAllByTestId('not-bd-item')[0]);
    await waitFor(() => expect(api.marcarNotifLeida).toHaveBeenCalledWith(
      expect.anything(), 'n1',
    ));
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/123');
  });

  it('click en ya-leída no llama marcar', async () => {
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getAllByTestId('not-bd-item'));
    await user.click(screen.getAllByTestId('not-bd-item')[1]);
    expect(api.marcarNotifLeida).not.toHaveBeenCalled();
  });

  it('marcar todas leídas', async () => {
    api.marcarNotifsTodasLeidas.mockResolvedValue({});
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-bd-marcar-todas'));
    await user.click(screen.getByTestId('not-bd-marcar-todas'));
    await waitFor(() => expect(api.marcarNotifsTodasLeidas).toHaveBeenCalled());
  });

  it('filtros', async () => {
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-bd-filtros'));
    await user.selectOptions(screen.getByTestId('not-bd-tipo'), 'sistema');
    await waitFor(() => expect(api.listNotificacionesInbox).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ tipo: 'sistema' }),
    ));
  });

  it('filtro leida=false', async () => {
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-bd-leida'));
    await user.selectOptions(screen.getByTestId('not-bd-leida'), 'false');
    await waitFor(() => expect(api.listNotificacionesInbox).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ leida: false }),
    ));
  });

  it('error', async () => {
    api.listNotificacionesInbox.mockRejectedValue(new Error('e'));
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-bd-error'));
  });

  it('empty', async () => {
    api.listNotificacionesInbox.mockResolvedValue({ items: [], total: 0, no_leidas: 0 });
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-bd-empty'));
  });

  it('click en notif sin link no falla', async () => {
    api.listNotificacionesInbox.mockResolvedValue({
      items: [{ id: 'nx', titulo: 'X', mensaje: 'm',
        leida: false, creado_en: '2026-05-27T00:00:00Z' }],
      total: 1, no_leidas: 1,
    });
    api.marcarNotifLeida.mockResolvedValue({});
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('not-bd-item'));
    await user.click(screen.getByTestId('not-bd-item'));
    await waitFor(() => expect(api.marcarNotifLeida).toHaveBeenCalled());
  });

  it('marcar leída con error swallow', async () => {
    api.marcarNotifLeida.mockRejectedValue(new Error('e'));
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BandejaNotificaciones session={{ token: 't' }} roles={ROLES}
      onNavigate={onNavigate} />);
    await waitFor(() => screen.getAllByTestId('not-bd-item'));
    await user.click(screen.getAllByTestId('not-bd-item')[0]);
    // El navigate aún sucede aunque marcar falle.
    expect(onNavigate).toHaveBeenCalled();
  });
});
