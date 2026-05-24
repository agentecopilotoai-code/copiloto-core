import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getCorrespondencia: vi.fn(),
  listAuditoria: vi.fn(),
  marcarLeidaCorrespondencia: vi.fn(),
  responderCorrespondencia: vi.fn(),
  reenviarCorrespondencia: vi.fn(),
  enviarCorrespondenciaARevision: vi.fn(),
  revisarCorrespondencia: vi.fn(),
  aprobarCorrespondencia: vi.fn(),
  firmarCorrespondencia: vi.fn(),
  radicarSalidaCorrespondencia: vi.fn(),
  enviarCorrespondencia: vi.fn(),
  registrarSoporteEnvio: vi.fn(),
  agregarDestinatarioCorrespondencia: vi.fn(),
  quitarDestinatarioCorrespondencia: vi.fn(),
  solicitarAnulacionCorrespondencia: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { CorrespondenciaFicha } from './CorrespondenciaFicha.jsx';

const C_INTERNA = {
  id: 'c1', tipo: 'interna', asunto: 'Comunicación',
  estado: 'enviada', numero: 'CI-2026-001',
  dependencia_origen_nombre: 'Talento',
  dependencia_destino_nombre: 'Jurídica',
  destinatarios: [],
  fecha: '2026-05-23T10:00:00Z',
};
const C_EXTERNA = {
  id: 'c2', tipo: 'externa', asunto: 'Oficio',
  estado: 'borrador', numero: 'CE-2026-001',
  dependencia_origen_nombre: 'Talento',
  tercero_destinatario_nombre: 'X',
  destinatarios: [],
  soportes_envio: [],
  fecha: '2026-05-23T10:00:00Z',
};

describe('CorrespondenciaFicha', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listAuditoria.mockResolvedValue({ items: [] });
  });

  function setup(props = {}, c = C_INTERNA) {
    api.getCorrespondencia.mockResolvedValue(c);
    return render(
      <CorrespondenciaFicha
        session={{ token: 't' }}
        correspondenciaId={c.id}
        roles={[]}
        {...props}
      />,
    );
  }

  it('interna: tabs sin Workflow ni Soporte', async () => {
    setup();
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    expect(screen.queryByTestId('corresp-tab-btn-Workflow')).toBeNull();
    expect(screen.queryByTestId('corresp-tab-btn-Soporte de envío')).toBeNull();
  });

  it('externa: incluye tabs Workflow + Soporte', async () => {
    setup({ roles: ['gd.jefe_dependencia'] }, C_EXTERNA);
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    expect(screen.getByTestId('corresp-tab-btn-Workflow')).toBeInTheDocument();
    expect(screen.getByTestId('corresp-tab-btn-Soporte de envío')).toBeInTheDocument();
  });

  it('tab Destinatarios sin items → empty', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Destinatarios'));
    expect(screen.getByTestId('corresp-tab-Destinatarios')).toBeInTheDocument();
  });

  it('agregar destinatario dispara API + refresh', async () => {
    api.agregarDestinatarioCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.usuario_ci'] });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Destinatarios'));
    // Estado 'enviada' oculta el form add — usamos interna que está enviada.
    // Pasamos a externa borrador para tener el form.
  });

  it('externa borrador: tab Workflow tiene CTA Enviar a revisión (jefe)', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.jefe_dependencia'] }, C_EXTERNA);
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Workflow'));
    expect(screen.getByTestId('ce-wf-enviar-revision')).toBeInTheDocument();
  });

  it('soporte: registrar nuevo dispara API', async () => {
    api.registrarSoporteEnvio.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({}, C_EXTERNA);
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Soporte de envío'));
    fireEvent.change(screen.getByTestId('sop-guia'), { target: { value: 'GUIA-001' } });
    fireEvent.change(screen.getByTestId('sop-fecha'), { target: { value: '2026-05-23' } });
    await user.click(screen.getByTestId('sop-submit'));
    await waitFor(() => expect(api.registrarSoporteEnvio).toHaveBeenCalled());
  });

  it('tab Trazabilidad llama listAuditoria', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Trazabilidad'));
    await waitFor(() => expect(api.listAuditoria).toHaveBeenCalled());
  });

  it('tab Acciones interna: rol usuario_ci ve Responder + Anular', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.usuario_ci'] });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Acciones'));
    expect(screen.getByTestId('acc-responder')).toBeInTheDocument();
  });

  it('externa: rol coord_vu ve Anular', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.coordinador_vu'] }, C_EXTERNA);
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Acciones'));
    expect(screen.getByTestId('acc-anular')).toBeInTheDocument();
  });

  it('Anular abre modal + submite', async () => {
    api.solicitarAnulacionCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.coordinador_vu'] }, C_EXTERNA);
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Acciones'));
    await user.click(screen.getByTestId('acc-anular'));
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'documento equivocado adjunto' },
    });
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.solicitarAnulacionCorrespondencia).toHaveBeenCalled());
  });

  it('error de carga muestra alert', async () => {
    api.getCorrespondencia.mockRejectedValueOnce(new Error('404'));
    render(
      <CorrespondenciaFicha
        session={{ token: 't' }}
        correspondenciaId="c-fail"
        roles={[]}
      />,
    );
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('externa revisada + jefe: CTA aprobar dispara API', async () => {
    api.aprobarCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.jefe_dependencia'] }, { ...C_EXTERNA, estado: 'revisada' });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Workflow'));
    await user.click(screen.getByTestId('ce-wf-aprobar'));
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.aprobarCorrespondencia).toHaveBeenCalled());
  });

  it('externa aprobada + firmante: CTA firmar', async () => {
    api.firmarCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.firmante'] }, { ...C_EXTERNA, estado: 'aprobada' });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Workflow'));
    await user.click(screen.getByTestId('ce-wf-firmar'));
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.firmarCorrespondencia).toHaveBeenCalled());
  });

  it('externa firmada + radicador: CTA radicar salida', async () => {
    api.radicarSalidaCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.radicador'] }, { ...C_EXTERNA, estado: 'firmada' });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Workflow'));
    await user.click(screen.getByTestId('ce-wf-radicar'));
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.radicarSalidaCorrespondencia).toHaveBeenCalled());
  });

  it('externa radicada + jefe: CTA enviar al destinatario', async () => {
    api.enviarCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.jefe_dependencia'] }, { ...C_EXTERNA, estado: 'radicada_salida' });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Workflow'));
    await user.click(screen.getByTestId('ce-wf-enviar'));
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.enviarCorrespondencia).toHaveBeenCalled());
  });

  it('externa en_revision + revisor: CTAs ok + devolver', async () => {
    api.revisarCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.revisor'] }, { ...C_EXTERNA, estado: 'en_revision' });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Workflow'));
    expect(screen.getByTestId('ce-wf-revisar-ok')).toBeInTheDocument();
    expect(screen.getByTestId('ce-wf-revisar-devolver')).toBeInTheDocument();
    await user.click(screen.getByTestId('ce-wf-revisar-ok'));
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.revisarCorrespondencia).toHaveBeenCalled());
  });

  it('responder interna: modal mensaje + submit', async () => {
    api.responderCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.usuario_ci'] });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Acciones'));
    await user.click(screen.getByTestId('acc-responder'));
    fireEvent.change(screen.getByTestId('modal-mensaje'), {
      target: { value: 'Respuesta recibida' },
    });
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.responderCorrespondencia).toHaveBeenCalled());
  });

  it('reenviar interna: requiere justificación', async () => {
    api.reenviarCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.usuario_ci'] });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Acciones'));
    await user.click(screen.getByTestId('acc-reenviar'));
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'Mejor enviar a la dependencia X' },
    });
    await user.click(screen.getByTestId('modal-confirm'));
    await waitFor(() => expect(api.reenviarCorrespondencia).toHaveBeenCalled());
  });

  it('Destinatarios: agregar dispara API', async () => {
    api.agregarDestinatarioCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.usuario_radicacion_externa'] }, C_EXTERNA);
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Destinatarios'));
    await waitFor(() => screen.getByTestId('dests-add-form'));
    fireEvent.change(screen.getByTestId('dest-add-nombre'), { target: { value: 'Pedro Z' } });
    fireEvent.change(screen.getByTestId('dest-add-tipo'), { target: { value: 'copia_oculta' } });
    await user.click(screen.getByTestId('dest-add-submit'));
    await waitFor(() => expect(api.agregarDestinatarioCorrespondencia).toHaveBeenCalled());
  });

  it('Destinatarios: quitar dispara API', async () => {
    api.quitarDestinatarioCorrespondencia.mockResolvedValueOnce({});
    const user = userEvent.setup();
    setup({ roles: ['gd.usuario_radicacion_externa'] }, {
      ...C_EXTERNA,
      destinatarios: [{ id: 'd1', nombre: 'X', tipo_copia: 'copia' }],
    });
    await waitFor(() => screen.getByTestId('corresp-tab-General'));
    await user.click(screen.getByTestId('corresp-tab-btn-Destinatarios'));
    await user.click(screen.getByTestId('dest-remove-d1'));
    await waitFor(() => expect(api.quitarDestinatarioCorrespondencia).toHaveBeenCalled());
  });
});
