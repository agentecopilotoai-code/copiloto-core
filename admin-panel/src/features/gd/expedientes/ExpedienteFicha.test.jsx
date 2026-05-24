import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getExpediente: vi.fn(),
  listDocumentosExpediente: vi.fn(),
  getIndiceExpediente: vi.fn(),
  agregarDocumentoExpediente: vi.fn(),
  quitarDocumentoExpediente: vi.fn(),
  cerrarExpediente: vi.fn(),
  transferirExpediente: vi.fn(),
  reabrirExpediente: vi.fn(),
  getActaCierreExpediente: vi.fn(),
}));
vi.mock('../hooks/useGdAudit.js', () => ({
  useGdAudit: () => ({ events: [], loading: false, error: null }),
}));
import * as api from '../services/gdApi.js';

import { ExpedienteFicha } from './ExpedienteFicha.jsx';

const ROLES = ['gd.admin_documental'];
const EXP = {
  id: 'e1', codigo: 'EXP-001', titulo: 'Convenio 001',
  serie_codigo: 'S001', serie_nombre: 'Contratos',
  subserie_codigo: 'S001.1', subserie_nombre: 'Servicios',
  dependencia_nombre: 'Talento',
  estado: 'abierto', fecha_apertura: '2026-01-01',
  total_documentos: 3, descripcion: 'd',
  responsable_nombre: 'Ana',
};
const DOC = {
  id: 'd1', documento_id: 'd1', folio: 1, titulo: 'Oficio inicial',
  tipo: 'oficio', incorporado_en: '2026-01-02', responsable_nombre: 'Ana',
};

describe('ExpedienteFicha', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getExpediente.mockResolvedValue(EXP);
    api.listDocumentosExpediente.mockResolvedValue({ items: [DOC] });
    api.getIndiceExpediente.mockResolvedValue({
      total_folios: 3, generado_en: '2026-05-20T10:00:00Z',
    });
  });

  it('renderiza tabs y tab General', async () => {
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('exp-tabs')).toBeInTheDocument());
    expect(screen.getByTestId('exp-tab-General')).toBeInTheDocument();
  });

  it('tab Documentos carga índice + docs', async () => {
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Documentos'));
    await waitFor(() => expect(screen.getByTestId('exp-docs-table')).toBeInTheDocument());
  });

  it('docs empty', async () => {
    api.listDocumentosExpediente.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Documentos'));
    await waitFor(() => expect(screen.getByTestId('exp-docs-empty')).toBeInTheDocument());
  });

  it('tab Acciones muestra CTAs cuando abierto y con permiso', async () => {
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Acciones'));
    expect(screen.getByTestId('exp-agregar-doc')).toBeInTheDocument();
    expect(screen.getByTestId('exp-cerrar')).toBeInTheDocument();
  });

  it('agregar documento submit OK', async () => {
    api.agregarDocumentoExpediente.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Acciones'));
    await user.click(screen.getByTestId('exp-agregar-doc'));
    fireEvent.change(screen.getByTestId('exp-agregar-uuid'), { target: { value: 'doc-uuid' } });
    await user.click(screen.getByTestId('exp-agregar-submit'));
    await waitFor(() => expect(api.agregarDocumentoExpediente).toHaveBeenCalledWith({ token: 't' }, 'e1', 'doc-uuid'));
  });

  it('quitar documento desde tabla con motivo', async () => {
    api.quitarDocumentoExpediente.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Documentos'));
    await waitFor(() => screen.getByTestId('exp-quitar-doc'));
    await user.click(screen.getByTestId('exp-quitar-doc'));
    fireEvent.change(screen.getByLabelText(/Motivo del retiro/i), { target: { value: 'duplicado con otro expediente' } });
    await user.click(screen.getByTestId('exp-quitar-submit'));
    await waitFor(() => expect(api.quitarDocumentoExpediente).toHaveBeenCalled());
  });

  it('expediente cerrado oculta CTAs de mod', async () => {
    api.getExpediente.mockResolvedValue({ ...EXP, estado: 'cerrado' });
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Acciones'));
    expect(screen.queryByTestId('exp-agregar-doc')).toBeNull();
    expect(screen.getByTestId('exp-reabrir')).toBeInTheDocument();
  });

  it('reabrir con motivo', async () => {
    api.getExpediente.mockResolvedValue({ ...EXP, estado: 'cerrado' });
    api.reabrirExpediente.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Acciones'));
    await user.click(screen.getByTestId('exp-reabrir'));
    fireEvent.change(screen.getByLabelText(/Motivo de reapertura/i), { target: { value: 'pendiente incorporar acta complementaria' } });
    await user.click(screen.getByTestId('exp-reabrir-submit'));
    await waitFor(() => expect(api.reabrirExpediente).toHaveBeenCalled());
  });

  it('click doc en tabla navega', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('exp-tabs'));
    await user.click(screen.getByTestId('exp-tab-btn-Documentos'));
    await waitFor(() => screen.getByTestId('exp-doc-link'));
    await user.click(screen.getByTestId('exp-doc-link'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d1');
  });

  it('error', async () => {
    api.getExpediente.mockRejectedValue(new Error('e'));
    render(<ExpedienteFicha session={{ token: 't' }} expedienteId="e1" roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
