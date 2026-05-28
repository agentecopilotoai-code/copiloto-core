import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listAlertasCriticas: vi.fn(),
  atenderAlertaCritica: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { AlertasCriticas } from './AlertasCriticas.jsx';

const ALERTAS = {
  items: [
    { id: 'a1', categoria: 'vencimiento', severidad: 'alta',
      titulo: 'PQRSD por vencer', descripcion: '5 días para vencer',
      entidad: { tipo: 'pqrsd', id: 'p1' }, creada_en: '2026-05-27T08:00:00Z',
      atendida_por: null },
    { id: 'a2', categoria: 'sla', severidad: 'media',
      titulo: 'SLA vulnerado', entidad: { tipo: 'pqrsd', id: 'p2' },
      creada_en: '2026-05-27T07:00:00Z',
      atendida_por: 'u1', atendida_en: '2026-05-27T07:30:00Z' },
  ],
  total_pendientes: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listAlertasCriticas.mockResolvedValue(ALERTAS);
});

describe('AlertasCriticas', () => {
  it('sin permiso → aviso', () => {
    render(<AlertasCriticas session={{}} roles={['gd.profesional']} />);
    expect(screen.getByTestId('alr-no-perm')).toBeInTheDocument();
  });

  it('admin sistema ve tabla + badge', async () => {
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => expect(screen.getAllByTestId('alr-row')).toHaveLength(2));
    expect(screen.getByTestId('alr-badge-pendientes').textContent).toMatch(/1/);
  });

  it('atender alerta requiere comentario', async () => {
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('alr-atender'));
    await user.click(screen.getByTestId('alr-atender'));
    expect(screen.getByTestId('alr-modal-confirmar')).toBeDisabled();
  });

  it('atender alerta ok', async () => {
    api.atenderAlertaCritica.mockResolvedValue({});
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('alr-atender'));
    await user.click(screen.getByTestId('alr-atender'));
    await user.type(screen.getByTestId('alr-modal-comentario'), 'Resuelto manualmente');
    await user.click(screen.getByTestId('alr-modal-confirmar'));
    await waitFor(() => expect(api.atenderAlertaCritica).toHaveBeenCalledWith(
      expect.anything(), 'a1', 'Resuelto manualmente',
    ));
  });

  it('cancelar modal', async () => {
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(await screen.findByTestId('alr-atender'));
    await user.click(screen.getByTestId('alr-modal-cancelar'));
    expect(screen.queryByTestId('alr-modal')).toBeNull();
  });

  it('atender con error muestra feedback', async () => {
    api.atenderAlertaCritica.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(await screen.findByTestId('alr-atender'));
    await user.type(screen.getByTestId('alr-modal-comentario'), 'x');
    await user.click(screen.getByTestId('alr-modal-confirmar'));
    await waitFor(() => expect(screen.getByTestId('alr-feedback').textContent).toMatch(/boom/));
  });

  it('ir a entidad', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']}
      onNavigate={onNavigate} />);
    await waitFor(() => screen.getAllByTestId('alr-ir-entidad'));
    await user.click(screen.getAllByTestId('alr-ir-entidad')[0]);
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/p1');
  });

  it('filtros', async () => {
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('alr-filtros'));
    await user.selectOptions(screen.getByTestId('alr-categoria'), 'vencimiento');
    await waitFor(() => expect(api.listAlertasCriticas).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ categoria: 'vencimiento' }),
    ));
  });

  it('filtro severidad', async () => {
    const user = userEvent.setup();
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('alr-severidad'));
    await user.selectOptions(screen.getByTestId('alr-severidad'), 'alta');
    await waitFor(() => expect(api.listAlertasCriticas).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ severidad: 'alta' }),
    ));
  });

  it('auditor solo lee (no botón atender)', async () => {
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.auditor']} />);
    await waitFor(() => screen.getAllByTestId('alr-row'));
    expect(screen.queryByTestId('alr-atender')).toBeNull();
  });

  it('error', async () => {
    api.listAlertasCriticas.mockRejectedValue(new Error('e'));
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('alr-error'));
  });

  it('empty', async () => {
    api.listAlertasCriticas.mockResolvedValue({ items: [], total_pendientes: 0 });
    render(<AlertasCriticas session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('alr-empty'));
  });
});
