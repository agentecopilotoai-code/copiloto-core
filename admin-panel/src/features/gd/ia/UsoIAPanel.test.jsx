import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getUsoIa: vi.fn(),
  getLimitesIa: vi.fn(),
  actualizarLimitesIa: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { UsoIAPanel } from './UsoIAPanel.jsx';

const USO = {
  total_tokens: 50000, total_coste_usd: 12.34,
  limite_actual_usd: 50, limite_consumido_usd: 12.34,
  por_modelo: [
    { codigo: 'gpt-4', llamadas: 100, tokens: 30000, coste_usd: 8.0 },
    { codigo: 'claude-3', llamadas: 50, tokens: 20000, coste_usd: 4.34 },
  ],
  por_usuario: [
    { usuario_id: 'u1', nombre: 'Alice', tokens: 30000,
      coste_usd: 8.0, limite_diario_usd: 2.0, limite_mensual_usd: 60 },
  ],
  por_funcionalidad: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getUsoIa.mockResolvedValue(USO);
  api.getLimitesIa.mockResolvedValue({
    limite_diario_usd: 5, limite_mensual_usd: 150,
    consumido_dia: 1.2, consumido_mes: 12.34,
  });
});

describe('UsoIAPanel', () => {
  it('sin permiso muestra aviso', () => {
    render(<UsoIAPanel session={{}} roles={['gd.profesional']} />);
    expect(screen.getByTestId('ia-uso-no-perm')).toBeInTheDocument();
  });

  it('admin sistema renderiza KPIs y tablas', async () => {
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-kpis'));
    expect(screen.getByTestId('ia-uso-tabla-modelo')).toBeInTheDocument();
    expect(screen.getByTestId('ia-uso-tabla-usuario')).toBeInTheDocument();
  });

  it('jefe_dependencia ve panel R sin editar', async () => {
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => screen.getByTestId('ia-uso-kpis'));
    expect(screen.queryByTestId('ia-uso-editar')).toBeNull();
  });

  it('admin abre modal de edición y guarda', async () => {
    api.actualizarLimitesIa.mockResolvedValue({ aplicado: true });
    const user = userEvent.setup();
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-editar'));
    await user.click(screen.getByTestId('ia-uso-editar'));
    expect(screen.getByTestId('ia-uso-modal-edicion')).toBeInTheDocument();
    await user.clear(screen.getByTestId('ia-uso-edit-diario'));
    await user.type(screen.getByTestId('ia-uso-edit-diario'), '10');
    await user.type(screen.getByTestId('ia-uso-edit-motivo'), 'aumento Q3');
    await user.click(screen.getByTestId('ia-uso-edit-guardar'));
    await waitFor(() => expect(api.actualizarLimitesIa).toHaveBeenCalled());
  });

  it('cancelar cierra modal', async () => {
    const user = userEvent.setup();
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-editar'));
    await user.click(screen.getByTestId('ia-uso-editar'));
    await user.click(screen.getByTestId('ia-uso-edit-cancelar'));
    expect(screen.queryByTestId('ia-uso-modal-edicion')).toBeNull();
  });

  it('guardar con error muestra feedback rojo', async () => {
    api.actualizarLimitesIa.mockRejectedValue(new Error('rechazado'));
    const user = userEvent.setup();
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-editar'));
    await user.click(screen.getByTestId('ia-uso-editar'));
    await user.type(screen.getByTestId('ia-uso-edit-motivo'), 'm');
    await user.click(screen.getByTestId('ia-uso-edit-guardar'));
    await waitFor(() => expect(screen.getByTestId('ia-uso-feedback').textContent).toMatch(/rechazado/));
  });

  it('error de uso', async () => {
    api.getUsoIa.mockRejectedValue(new Error('e'));
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-error'));
  });

  it('filtros disparan refetch', async () => {
    const user = userEvent.setup();
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-filtros'));
    await user.type(screen.getByTestId('ia-uso-modelo'), 'gpt-4');
    await waitFor(() => expect(api.getUsoIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ modelo: 'gpt-4' }),
    ));
  });

  it('refresh button', async () => {
    const user = userEvent.setup();
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-refresh'));
    api.getUsoIa.mockClear();
    await user.click(screen.getByTestId('ia-uso-refresh'));
    await waitFor(() => expect(api.getUsoIa).toHaveBeenCalled());
  });

  it('% consumido alto pinta danger', async () => {
    api.getUsoIa.mockResolvedValue({
      ...USO, limite_actual_usd: 10, limite_consumido_usd: 9.5,
    });
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-kpis'));
    const danger = screen.getAllByText(/95\.0%|95%/).find(Boolean);
    expect(danger).toBeTruthy();
  });

  it('mis-limites se muestra si la API responde', async () => {
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-mis-limites'));
  });

  it('motivo vacío deshabilita guardar', async () => {
    const user = userEvent.setup();
    render(<UsoIAPanel session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('ia-uso-editar'));
    await user.click(screen.getByTestId('ia-uso-editar'));
    expect(screen.getByTestId('ia-uso-edit-guardar')).toBeDisabled();
  });
});
