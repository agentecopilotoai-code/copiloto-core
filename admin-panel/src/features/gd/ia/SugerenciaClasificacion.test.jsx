import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  sugerirClasificacionIa: vi.fn(),
  aplicarSugerenciaClasificacion: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { SugerenciaClasificacion } from './SugerenciaClasificacion.jsx';

const ROLES_OK = ['gd.profesional'];

const SUG = {
  trd_sugerida: { serie: '100', subserie: '110', retencion: 5 },
  tipo_documental: 'Memorando',
  dependencia: { id: 'd1', nombre: 'Jurídica' },
  confianza: 0.92, justificacion: 'asunto matches "memorando jurídico"',
};

beforeEach(() => vi.clearAllMocks());

describe('SugerenciaClasificacion', () => {
  it('sin permiso → no render', () => {
    const { container } = render(
      <SugerenciaClasificacion session={{}} roles={['gd.usuario_consulta']}
        entidad="documento" entidadId="d1" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('pedir sugerencia muestra resultado', async () => {
    api.sugerirClasificacionIa.mockResolvedValue(SUG);
    const user = userEvent.setup();
    render(
      <SugerenciaClasificacion session={{ token: 't' }} roles={ROLES_OK}
        entidad="documento" entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-sug-clasif-pedir'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-clasif-resultado')).toBeInTheDocument());
    expect(screen.getByTestId('ia-sug-clasif-confianza').textContent).toMatch(/92%/);
  });

  it('aceptar dispara onAplicar y muestra feedback', async () => {
    api.sugerirClasificacionIa.mockResolvedValue(SUG);
    api.aplicarSugerenciaClasificacion.mockResolvedValue({ aplicado: true, audit_id: 'a1' });
    const onAplicar = vi.fn();
    const user = userEvent.setup();
    render(
      <SugerenciaClasificacion session={{ token: 't' }} roles={ROLES_OK}
        entidad="documento" entidadId="d1" onAplicar={onAplicar} />,
    );
    await user.click(screen.getByTestId('ia-sug-clasif-pedir'));
    await waitFor(() => screen.getByTestId('ia-sug-clasif-aceptar'));
    await user.click(screen.getByTestId('ia-sug-clasif-aceptar'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-clasif-feedback')).toBeInTheDocument());
    expect(onAplicar).toHaveBeenCalledWith('aceptar', expect.objectContaining({ aplicado: true }));
  });

  it('rechazar también funciona', async () => {
    api.sugerirClasificacionIa.mockResolvedValue(SUG);
    api.aplicarSugerenciaClasificacion.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(
      <SugerenciaClasificacion session={{ token: 't' }} roles={ROLES_OK}
        entidad="documento" entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-sug-clasif-pedir'));
    await waitFor(() => screen.getByTestId('ia-sug-clasif-rechazar'));
    await user.click(screen.getByTestId('ia-sug-clasif-rechazar'));
    await waitFor(() => screen.getByTestId('ia-sug-clasif-feedback'));
  });

  it('error de budget muestra mensaje específico', async () => {
    const err = Object.assign(new Error('over budget'), { code: 'ia_budget_exceeded' });
    api.sugerirClasificacionIa.mockRejectedValue(err);
    const user = userEvent.setup();
    render(
      <SugerenciaClasificacion session={{ token: 't' }} roles={ROLES_OK}
        entidad="documento" entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-sug-clasif-pedir'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-clasif-error').textContent).toMatch(/Presupuesto/));
  });

  it('error de aplicar muestra feedback de error', async () => {
    api.sugerirClasificacionIa.mockResolvedValue(SUG);
    api.aplicarSugerenciaClasificacion.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(
      <SugerenciaClasificacion session={{ token: 't' }} roles={ROLES_OK}
        entidad="documento" entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-sug-clasif-pedir'));
    await waitFor(() => screen.getByTestId('ia-sug-clasif-aceptar'));
    await user.click(screen.getByTestId('ia-sug-clasif-aceptar'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-clasif-feedback').textContent).toMatch(/boom/));
  });

  it('confianza baja → badge danger', async () => {
    api.sugerirClasificacionIa.mockResolvedValue({ ...SUG, confianza: 0.4 });
    const user = userEvent.setup();
    render(
      <SugerenciaClasificacion session={{ token: 't' }} roles={ROLES_OK}
        entidad="documento" entidadId="d1" />,
    );
    await user.click(screen.getByTestId('ia-sug-clasif-pedir'));
    await waitFor(() => expect(screen.getByTestId('ia-sug-clasif-confianza').textContent).toMatch(/40%/));
  });
});
