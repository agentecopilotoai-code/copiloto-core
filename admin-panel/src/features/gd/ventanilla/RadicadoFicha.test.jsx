import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getRadicado: vi.fn(),
  reclasificarRadicado: vi.fn(),
  corregirDatosMenores: vi.fn(),
  solicitarAnulacionRadicado: vi.fn(),
  listAuditoria: vi.fn(),
}));
import {
  getRadicado,
  reclasificarRadicado,
  corregirDatosMenores,
  solicitarAnulacionRadicado,
  listAuditoria,
} from '../services/gdApi.js';

import { RadicadoFicha } from './RadicadoFicha.jsx';

const SESSION = { token: 't', tenant: { id: 'tnt' } };
const RAD = {
  id: 'r1',
  numero_radicado: '2026-E-001',
  tipo_radicado: 'entrada',
  estado: 'radicado',
  canal_nombre: 'Web',
  fecha_radicacion: '2026-05-23T10:00:00Z',
  asunto: 'Solicitud certificado',
  descripcion: 'Texto largo…',
  dependencia_actual_nombre: 'Talento',
  anexos: [{ id: 'a1', nombre: 'doc.pdf', mime_type: 'application/pdf', size: 1024 }],
  clasificacion_actual: { tipo_clasificacion: 'pqrsd', sub_tipo: 'P-1', dependencia_destino_nombre: 'Jurídica' },
  clasificacion_historial: [
    { id: 'h1', fecha: '2026-05-22T10:00:00Z', usuario_nombre: 'X', tipo_clasificacion: 'tramite', justificacion: 'error' },
  ],
};

describe('RadicadoFicha', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getRadicado.mockResolvedValue(RAD);
    listAuditoria.mockResolvedValue({ items: [] });
  });

  function setup(props = {}) {
    return render(
      <RadicadoFicha
        session={SESSION}
        radicadoId="r1"
        roles={['gd.coordinador_vu']}
        {...props}
      />,
    );
  }

  it('carga y renderiza tab General por default', async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId('tab-content-General')).toBeInTheDocument());
    // Numero aparece en header + tabla General; al menos 1.
    expect(screen.getAllByText('2026-E-001').length).toBeGreaterThanOrEqual(1);
  });

  it('error de carga muestra alert', async () => {
    getRadicado.mockRejectedValueOnce(new Error('404'));
    setup();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('cambiar a tab Anexos muestra archivos', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('tab-Anexos'));
    expect(screen.getByTestId('anexos-list')).toBeInTheDocument();
    expect(screen.getByText(/doc\.pdf/)).toBeInTheDocument();
  });

  it('tab Clasificación muestra actual + historial', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('tab-Clasificación'));
    expect(screen.getByText(/Clasificación actual/)).toBeInTheDocument();
    expect(screen.getByText(/Versiones anteriores/)).toBeInTheDocument();
  });

  it('tab Trazabilidad llama useGdAudit (listAuditoria)', async () => {
    const user = userEvent.setup();
    setup();
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('tab-Trazabilidad'));
    await waitFor(() => expect(listAuditoria).toHaveBeenCalled());
  });

  it('tab Acciones tiene CTAs según rol', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.coordinador_vu'] });
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('tab-Acciones'));
    expect(screen.getByTestId('tab-content-Acciones')).toBeInTheDocument();
    // "Reclasificar" aparece como botón en header + tab Acciones.
    expect(screen.getAllByText('Reclasificar').length).toBeGreaterThanOrEqual(1);
  });

  it('botón Reclasificar abre modal y submite', async () => {
    reclasificarRadicado.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    setup({ roles: ['gd.coordinador_vu'] });
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('btn-reclasificar'));
    expect(screen.getByTestId('ficha-modal')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('modal-tipo'), { target: { value: 'tramite' } });
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'cambio de tipo por error' },
    });
    await user.click(screen.getByTestId('modal-reclasif-submit'));
    await waitFor(() => expect(reclasificarRadicado).toHaveBeenCalled());
  });

  it('botón Solicitar anulación abre modal con motivo', async () => {
    solicitarAnulacionRadicado.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    setup({ roles: ['gd.radicador'] });
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('btn-anular'));
    expect(screen.getByTestId('ficha-modal')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'duplicado del radicado anterior' },
    });
    await user.click(screen.getByTestId('modal-anular-submit'));
    await waitFor(() => expect(solicitarAnulacionRadicado).toHaveBeenCalled());
  });

  it('botón Corregir abre modal y submite', async () => {
    corregirDatosMenores.mockResolvedValueOnce({ ok: true });
    const user = userEvent.setup();
    setup({ roles: ['gd.coordinador_vu'] });
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('btn-corregir'));
    fireEvent.change(screen.getByTestId('modal-corregir-asunto'), {
      target: { value: 'Asunto corregido' },
    });
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'typo en asunto original' },
    });
    await user.click(screen.getByTestId('modal-corregir-submit'));
    await waitFor(() => expect(corregirDatosMenores).toHaveBeenCalled());
  });

  it('rol sin permisos no ve botones de acción', async () => {
    setup({ roles: ['gd.usuario_consulta'] });
    await waitFor(() => screen.getByTestId('tab-content-General'));
    expect(screen.queryByTestId('btn-anular')).toBeNull();
    expect(screen.queryByTestId('btn-reclasificar')).toBeNull();
  });

  it('cerrar modal con click en backdrop', async () => {
    const user = userEvent.setup();
    setup({ roles: ['gd.coordinador_vu'] });
    await waitFor(() => screen.getByTestId('tab-content-General'));
    await user.click(screen.getByTestId('btn-reclasificar'));
    const modal = screen.getByTestId('ficha-modal');
    fireEvent.click(modal);  // backdrop
    await waitFor(() => expect(screen.queryByTestId('ficha-modal')).toBeNull());
  });
});
