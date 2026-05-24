import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getPQRSD: vi.fn(),
  listAuditoria: vi.fn(),
  asignarDependenciaPQRSD: vi.fn(),
  asignarFuncionarioPQRSD: vi.fn(),
  reasignarPQRSD: vi.fn(),
  proyectarRespuestaPQRSD: vi.fn(),
  enviarRespuestaARevision: vi.fn(),
  revisarRespuestaPQRSD: vi.fn(),
  aprobarRespuestaPQRSD: vi.fn(),
  firmarRespuestaPQRSD: vi.fn(),
  radicarSalidaRespuesta: vi.fn(),
  enviarRespuestaPQRSD: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { FichaPQRSD } from './FichaPQRSD.jsx';

const PQ_BASE = {
  id: 'p1', numero_radicado: '2026-P-001',
  tipo: 'P', tipo_nombre: 'Petición',
  estado: 'en_proyeccion',
  asunto: 'Solicitud',
  tercero_nombre: 'María',
  canal_nombre: 'Web',
  fecha_radicacion: '2026-05-23T10:00:00Z',
  fecha_vencimiento: '2026-06-10T10:00:00Z',
  dependencia_actual_nombre: 'Talento',
  responsable_nombre: 'Juan',
  dias_restantes: 12,
  termino_dias: 15,
  descripcion: 'Texto…',
  documentos: [{ id: 'd1', titulo: 'Borrador', tipo: 'respuesta', estado: 'borrador' }],
  respuesta_actual: null,
};

describe('FichaPQRSD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPQRSD.mockResolvedValue(PQ_BASE);
    api.listAuditoria.mockResolvedValue({ items: [] });
  });

  function setup(props = {}, pq = PQ_BASE) {
    api.getPQRSD.mockResolvedValue(pq);
    return render(<FichaPQRSD session={{ token: 't' }} pqrsdId="p1" roles={[]} {...props} />);
  }

  it('renderiza tab General por default', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('pqrsd-tab-btn-General')).toBeInTheDocument());
    expect(screen.getByText('Solicitud')).toBeInTheDocument();
  });

  it('error carga muestra alert', async () => {
    api.getPQRSD.mockRejectedValueOnce(new Error('e'));
    setup();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('tab Documentos muestra lista', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Documentos'));
    expect(screen.getByTestId('pqrsd-docs-list')).toBeInTheDocument();
    expect(screen.getByText(/Borrador/)).toBeInTheDocument();
  });

  it('tab Documentos empty cuando no hay docs', async () => {
    const user = userEvent.setup();
    setup({}, { ...PQ_BASE, documentos: [] });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Documentos'));
    expect(screen.getByTestId('pqrsd-docs-empty')).toBeInTheDocument();
  });

  it('tab Workflow sin respuesta + rol profesional muestra CTA proyectar', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.profesional'] });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Workflow'));
    expect(screen.getByTestId('wf-proyectar')).toBeInTheDocument();
  });

  it('Proyectar abre modal + submit dispara API', async () => {
    api.proyectarRespuestaPQRSD.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    setup({ roles: ['gd.profesional'] });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Workflow'));
    await user.click(screen.getByTestId('wf-proyectar'));
    fireEvent.change(screen.getByTestId('modal-contenido'), {
      target: { value: 'Texto borrador inicial de la respuesta' },
    });
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.proyectarRespuestaPQRSD).toHaveBeenCalled());
  });

  it('estado borrador + rol profesional → CTA enviar a revisión', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.profesional'] }, {
      ...PQ_BASE,
      respuesta_actual: { id: 'r1', estado: 'borrador', proyectada_por_nombre: 'X' },
    });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Workflow'));
    expect(screen.getByTestId('wf-enviar-revision')).toBeInTheDocument();
  });

  it('estado en_revision + rol revisor → ok + devolver', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.revisor'] }, {
      ...PQ_BASE,
      respuesta_actual: { id: 'r1', estado: 'en_revision', proyectada_por_nombre: 'X' },
    });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Workflow'));
    expect(screen.getByTestId('wf-revisar-ok')).toBeInTheDocument();
    expect(screen.getByTestId('wf-revisar-devolver')).toBeInTheDocument();
  });

  it('Devolver requiere justificación', async () => {
    api.revisarRespuestaPQRSD.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    setup({ roles: ['gd.revisor'] }, {
      ...PQ_BASE,
      respuesta_actual: { id: 'r1', estado: 'en_revision', proyectada_por_nombre: 'X' },
    });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Workflow'));
    await user.click(screen.getByTestId('wf-revisar-devolver'));
    expect(screen.getByTestId('modal-confirm')).toBeDisabled();
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'Falta soporte documental adjunto' },
    });
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.revisarRespuestaPQRSD).toHaveBeenCalled());
  });

  it('estado aprobada + firmante → CTA firmar', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.firmante'] }, {
      ...PQ_BASE,
      respuesta_actual: { id: 'r1', estado: 'aprobada' },
    });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Workflow'));
    expect(screen.getByTestId('wf-firmar')).toBeInTheDocument();
  });

  it('tab Trazabilidad llama listAuditoria', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Trazabilidad'));
    await waitFor(() => expect(api.listAuditoria).toHaveBeenCalled());
  });

  it('tab Acciones gated por permisos — coord PQRSD ve Reasignar', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.admin_pqrsd'] });
    await waitFor(() => screen.getByTestId('pqrsd-tab-btn-General'));
    await user.click(screen.getByTestId('pqrsd-tab-btn-Acciones'));
    expect(screen.getByTestId('acc-reasignar')).toBeInTheDocument();
  });
});
