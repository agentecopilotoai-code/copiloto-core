import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  buscarAuditoria: vi.fn(),
  exportarAuditoria: vi.fn(),
  listCatalogoEntidadesAuditoria: vi.fn(),
  listCatalogoAccionesAuditoria: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { BandejaAuditoria } from './BandejaAuditoria.jsx';

const ROLES = ['gd.auditor'];
const EV = {
  id: 'e1', actor_email: 'admin@x.gov.co', accion: 'crear',
  entidad_tipo: 'pqrsd', entidad_id: 'abcdef1234567890',
  ip: '10.0.0.1', hash: 'sha256-abcdef1234567890', created_at: '2026-05-23T10:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.buscarAuditoria.mockResolvedValue({ items: [EV], total: 1 });
  api.listCatalogoEntidadesAuditoria.mockResolvedValue([{ codigo: 'pqrsd', nombre: 'PQRSD' }]);
  api.listCatalogoAccionesAuditoria.mockResolvedValue([{ codigo: 'crear', nombre: 'Crear' }]);
});

describe('BandejaAuditoria', () => {
  it('renderiza tabla + filtros', async () => {
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('aud-table')).toBeInTheDocument());
    expect(screen.getByTestId('aud-filter-actor')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.buscarAuditoria.mockResolvedValue({ items: [], total: 0 });
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('aud-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.buscarAuditoria.mockRejectedValue(new Error('e'));
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('filtros disparan refetch', async () => {
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.buscarAuditoria).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('aud-filter-actor'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByTestId('aud-filter-entidad'), { target: { value: 'pqrsd' } });
    fireEvent.change(screen.getByTestId('aud-filter-accion'), { target: { value: 'crear' } });
    fireEvent.change(screen.getByTestId('aud-filter-desde'), { target: { value: '2026-01-01' } });
    await waitFor(() => expect(api.buscarAuditoria).toHaveBeenCalledTimes(5));
  });

  it('click en row navega a ficha', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('aud-row'));
    await user.click(screen.getByTestId('aud-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/auditoria/e1');
  });

  it('exportar CSV con permiso', async () => {
    api.exportarAuditoria.mockResolvedValue({ url_descarga: 'https://x/a.csv' });
    const user = userEvent.setup();
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('aud-export-csv'));
    await waitFor(() => expect(screen.getByTestId('aud-export-info').textContent).toMatch(/csv/));
    expect(api.exportarAuditoria).toHaveBeenCalled();
  });

  it('exportar error', async () => {
    api.exportarAuditoria.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('aud-export-csv'));
    await waitFor(() => expect(screen.getByTestId('aud-export-info').textContent).toMatch(/boom/));
  });

  it('sin permiso AUD-005 oculta exportar', async () => {
    render(<BandejaAuditoria session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('aud-table'));
    expect(screen.queryByTestId('aud-export-csv')).toBeNull();
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<BandejaAuditoria session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('aud-table'));
    await user.click(screen.getByTestId('aud-refresh'));
    expect(api.buscarAuditoria).toHaveBeenCalledTimes(2);
  });
});
