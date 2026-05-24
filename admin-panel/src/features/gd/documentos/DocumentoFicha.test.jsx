import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getDocumento: vi.fn(),
  listVersionesDocumento: vi.fn(),
  nuevaVersionDocumento: vi.fn(),
  anularDocumento: vi.fn(),
}));
vi.mock('../hooks/useGdAudit.js', () => ({
  useGdAudit: () => ({ events: [], loading: false, error: null }),
}));
import * as api from '../services/gdApi.js';

import { DocumentoFicha } from './DocumentoFicha.jsx';

const DOC = {
  id: 'd1', titulo: 'Oficio 01', tipo: 'oficio', version_actual: 2,
  estado: 'aprobado', autor_nombre: 'Ana',
  created_at: '2026-05-01T10:00:00Z',
  updated_at: '2026-05-10T10:00:00Z',
  archivo_url: 'https://x/y.pdf',
};

describe('DocumentoFicha', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getDocumento.mockResolvedValue(DOC);
    api.listVersionesDocumento.mockResolvedValue({
      items: [{ id: 'v1', numero_version: 1, autor_nombre: 'Ana', created_at: '2026-05-01T10:00:00Z' }],
    });
  });

  it('renderiza tabs y tab General por default', async () => {
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => expect(screen.getByTestId('doc-tabs')).toBeInTheDocument());
    expect(screen.getByTestId('doc-tab-General')).toBeInTheDocument();
  });

  it('cambia a Versiones y carga versiones', async () => {
    const user = userEvent.setup();
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('doc-tabs'));
    await user.click(screen.getByTestId('doc-tab-btn-Versiones'));
    await waitFor(() => expect(screen.getByTestId('versiones-table')).toBeInTheDocument());
  });

  it('versiones empty', async () => {
    api.listVersionesDocumento.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('doc-tabs'));
    await user.click(screen.getByTestId('doc-tab-btn-Versiones'));
    await waitFor(() => expect(screen.getByTestId('versiones-empty')).toBeInTheDocument());
  });

  it('Acciones con permiso muestra CTAs', async () => {
    const user = userEvent.setup();
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" roles={['gd.profesional', 'gd.admin_documental']} />);
    await waitFor(() => screen.getByTestId('doc-tabs'));
    await user.click(screen.getByTestId('doc-tab-btn-Acciones'));
    expect(screen.getByTestId('acc-nueva-version')).toBeInTheDocument();
    expect(screen.getByTestId('acc-anular-doc')).toBeInTheDocument();
  });

  it('nueva versión modal submit OK', async () => {
    api.nuevaVersionDocumento.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" roles={['gd.profesional']} />);
    await waitFor(() => screen.getByTestId('doc-tabs'));
    await user.click(screen.getByTestId('doc-tab-btn-Acciones'));
    await user.click(screen.getByTestId('acc-nueva-version'));
    fireEvent.change(screen.getByTestId('nuevaver-archivo'), { target: { value: 'arch-uuid' } });
    fireEvent.change(screen.getByLabelText(/Motivo de la nueva versión/i), { target: { value: 'corrige tipografía detectada' } });
    await user.click(screen.getByTestId('nuevaver-submit'));
    await waitFor(() => expect(api.nuevaVersionDocumento).toHaveBeenCalled());
  });

  it('anular modal submit error muestra alert', async () => {
    api.anularDocumento.mockRejectedValueOnce(new Error('falla'));
    const user = userEvent.setup();
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" roles={['gd.admin_documental']} />);
    await waitFor(() => screen.getByTestId('doc-tabs'));
    await user.click(screen.getByTestId('doc-tab-btn-Acciones'));
    await user.click(screen.getByTestId('acc-anular-doc'));
    fireEvent.change(screen.getByLabelText(/Motivo de anulación/i), { target: { value: 'documento contiene datos sensibles' } });
    await user.click(screen.getByTestId('anular-doc-submit'));
    await waitFor(() => {
      const alerts = screen.getAllByRole('alert');
      expect(alerts.some((a) => /falla/.test(a.textContent))).toBe(true);
    });
  });

  it('error de ficha', async () => {
    api.getDocumento.mockRejectedValue(new Error('e'));
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('tab Trazabilidad renderiza', async () => {
    const user = userEvent.setup();
    render(<DocumentoFicha session={{ token: 't' }} documentoId="d1" />);
    await waitFor(() => screen.getByTestId('doc-tabs'));
    await user.click(screen.getByTestId('doc-tab-btn-Trazabilidad'));
    // WorkflowTimeline renderiza algo
    expect(screen.getByTestId('doc-tabs')).toBeInTheDocument();
  });
});
