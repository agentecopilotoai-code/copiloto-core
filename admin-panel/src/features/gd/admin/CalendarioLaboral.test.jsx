import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  getCalendarioLaboral: vi.fn(),
  agregarDiaFestivo: vi.fn(),
  quitarDiaFestivo: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { CalendarioLaboral } from './CalendarioLaboral.jsx';

const ROLES = ['gd.admin_sistema'];
const F = { id: 'f1', fecha: '2026-07-20', descripcion: 'Independencia', tipo: 'festivo' };

describe('CalendarioLaboral', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getCalendarioLaboral.mockResolvedValue({ festivos: [F] });
  });

  it('renderiza tabla', async () => {
    render(<CalendarioLaboral session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('cal-table')).toBeInTheDocument());
  });

  it('empty', async () => {
    api.getCalendarioLaboral.mockResolvedValue({ festivos: [] });
    render(<CalendarioLaboral session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('cal-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.getCalendarioLaboral.mockRejectedValue(new Error('e'));
    render(<CalendarioLaboral session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('cambiar año dispara refetch', async () => {
    render(<CalendarioLaboral session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.getCalendarioLaboral).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('cal-anio'), { target: { value: '2027' } });
    await waitFor(() => expect(api.getCalendarioLaboral).toHaveBeenCalledTimes(2));
  });

  it('agregar día festivo', async () => {
    api.agregarDiaFestivo.mockResolvedValue({ id: 'f2' });
    const user = userEvent.setup();
    render(<CalendarioLaboral session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cal-agregar'));
    fireEvent.change(screen.getByTestId('cal-agregar-fecha'), { target: { value: '2026-08-07' } });
    fireEvent.change(screen.getByTestId('cal-agregar-desc'), { target: { value: 'Batalla de Boyacá' } });
    fireEvent.change(screen.getByTestId('cal-agregar-tipo'), { target: { value: 'conmemoracion' } });
    await user.click(screen.getByTestId('cal-agregar-submit'));
    await waitFor(() => expect(api.agregarDiaFestivo).toHaveBeenCalled());
  });

  it('quitar día con motivo', async () => {
    api.quitarDiaFestivo.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<CalendarioLaboral session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('cal-row'));
    await user.click(screen.getByTestId('cal-quitar'));
    fireEvent.change(screen.getByLabelText(/Motivo del cambio/i), { target: { value: 'corrección por decreto' } });
    await user.click(screen.getByTestId('cal-quitar-submit'));
    await waitFor(() => expect(api.quitarDiaFestivo).toHaveBeenCalled());
  });

  it('sin permiso oculta CTAs', async () => {
    render(<CalendarioLaboral session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await waitFor(() => screen.getByTestId('cal-table'));
    expect(screen.queryByTestId('cal-agregar')).toBeNull();
    expect(screen.queryByTestId('cal-quitar')).toBeNull();
  });
});
