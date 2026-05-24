import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getEstadoBackups: vi.fn(),
  dispararBackupManual: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { Backup } from './Backup.jsx';

const ROLES = ['gd.admin_sistema'];
const B = {
  id: 'b1', iniciado_en: '2026-05-23 02:00', tipo: 'auto', estado: 'exitoso',
  tamano_mb: 1240, hash: 'sha256-abcdef1234567890', duracion_seg: 87,
};

describe('Backup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getEstadoBackups.mockResolvedValue({
      items: [B], proximo_backup: '2026-05-24 02:00', frecuencia: 'diario',
    });
  });

  it('tabla con backups', async () => {
    render(<Backup session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('bak-table')).toBeInTheDocument());
    expect(screen.getByTestId('bak-proximo')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.getEstadoBackups.mockResolvedValue({ items: [] });
    render(<Backup session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('bak-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.getEstadoBackups.mockRejectedValue(new Error('e'));
    render(<Backup session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('backup manual con motivo OK', async () => {
    api.dispararBackupManual.mockResolvedValue({ id: 'b2' });
    const user = userEvent.setup();
    render(<Backup session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('bak-manual'));
    fireEvent.change(screen.getByLabelText(/Motivo del backup/i), { target: { value: 'previo a despliegue mayor' } });
    await user.click(screen.getByTestId('bak-manual-submit'));
    await waitFor(() => expect(api.dispararBackupManual).toHaveBeenCalled());
  });

  it('backup manual error', async () => {
    api.dispararBackupManual.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<Backup session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('bak-manual'));
    fireEvent.change(screen.getByLabelText(/Motivo del backup/i), { target: { value: 'prueba operativa programada' } });
    await user.click(screen.getByTestId('bak-manual-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<Backup session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('bak-table'));
    await user.click(screen.getByTestId('bak-refresh'));
    expect(api.getEstadoBackups).toHaveBeenCalledTimes(2);
  });
});
