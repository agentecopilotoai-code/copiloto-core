import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getBuzonDependencia: vi.fn(),
  getCargaEquipo: vi.fn(),
}));
import { getBuzonDependencia, getCargaEquipo } from '../services/gdApi.js';

import { BuzonDependencia } from './BuzonDependencia.jsx';

describe('BuzonDependencia', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getBuzonDependencia.mockResolvedValue({
      items: [{ id: 'i1', titulo: 'Caso 1', responsable_nombre: 'María' }],
      contadores: {},
      total: 1,
    });
  });

  it('renderiza grid + tab por default = Buzón', async () => {
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => expect(screen.getByTestId('dep-buzon-grid')).toBeInTheDocument());
  });

  it('Carga del equipo gated por PERM-REP-009', async () => {
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.usuario_dependencia']} />);
    await waitFor(() => screen.getByTestId('dep-buzon-grid'));
    const tab = screen.getByTestId('dep-tab-Carga del equipo');
    expect(tab).toBeDisabled();
  });

  it('cambiar a tab Carga llama getCargaEquipo', async () => {
    getCargaEquipo.mockResolvedValue({
      usuarios: [
        { user_id: 'u1', nombre: 'Ana', cargo: 'Prof', tareas_abiertas: 4, vencimientos_proximos: 1, productividad: 92 },
      ],
    });
    const user = userEvent.setup();
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => screen.getByTestId('dep-buzon-grid'));
    await user.click(screen.getByTestId('dep-tab-Carga del equipo'));
    await waitFor(() => expect(screen.getByTestId('carga-equipo')).toBeInTheDocument());
    expect(screen.getByText('Ana')).toBeInTheDocument();
  });

  it('carga equipo empty', async () => {
    getCargaEquipo.mockResolvedValue({ usuarios: [] });
    const user = userEvent.setup();
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => screen.getByTestId('dep-buzon-grid'));
    await user.click(screen.getByTestId('dep-tab-Carga del equipo'));
    await waitFor(() => expect(screen.getByTestId('carga-empty')).toBeInTheDocument());
  });

  it('error en carga equipo muestra alert', async () => {
    getCargaEquipo.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => screen.getByTestId('dep-buzon-grid'));
    await user.click(screen.getByTestId('dep-tab-Carga del equipo'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('click en item de buzón muestra detalle', async () => {
    const user = userEvent.setup();
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => screen.getAllByTestId('dep-item'));
    await user.click(screen.getAllByTestId('dep-item')[0]);
    // detalle renderizado tras selección
  });

  it('cambiar carpeta dispara nuevo fetch', async () => {
    const user = userEvent.setup();
    render(<BuzonDependencia session={{ token: 't' }} roles={['gd.jefe_dependencia']} />);
    await waitFor(() => expect(getBuzonDependencia).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('dep-carpeta-tareas'));
    await waitFor(() => expect(getBuzonDependencia).toHaveBeenCalledTimes(2));
  });
});
