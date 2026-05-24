import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listAlertasPii: vi.fn(),
  detectarPiiIA: vi.fn(),
  marcarAlertaPiiAtendida: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { DeteccionPII } from './DeteccionPII.jsx';

const ROLES = ['gd.admin_sistema'];
const A = {
  id: 'a1', severidad: 'alta', tipos: ['cedula', 'correo'],
  documento_id: 'd1abcdef', documento_titulo: 'Resolución 001',
  detectada_en: '2026-05-23T10:00:00Z', estado: 'pendiente',
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listAlertasPii.mockResolvedValue({ items: [A], total: 1 });
});

describe('DeteccionPII', () => {
  it('sin permiso muestra warning', () => {
    render(<DeteccionPII session={{ token: 't' }} roles={['gd.firmante']} />);
    expect(screen.getByTestId('ia-pii-no-perm')).toBeInTheDocument();
  });

  it('tabla con alertas', async () => {
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('ia-pii-table')).toBeInTheDocument());
    expect(screen.getByTestId('ia-pii-row')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listAlertasPii.mockResolvedValue({ items: [], total: 0 });
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('ia-pii-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listAlertasPii.mockRejectedValue(new Error('e'));
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('atender alerta con motivo', async () => {
    api.marcarAlertaPiiAtendida.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('ia-pii-row'));
    await user.click(screen.getByTestId('ia-pii-atender'));
    fireEvent.change(screen.getByLabelText(/Acción tomada/i), { target: { value: 'datos enmascarados en el doc' } });
    await user.click(screen.getByTestId('ia-pii-atender-submit'));
    await waitFor(() => expect(api.marcarAlertaPiiAtendida).toHaveBeenCalled());
  });

  it('analizar texto inline', async () => {
    api.detectarPiiIA.mockResolvedValue({
      severidad_max: 'alta',
      detecciones: [
        { tipo: 'cedula', fragmento: '12345', severidad: 'alta' },
      ],
    });
    const user = userEvent.setup();
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('ia-pii-analizar'));
    fireEvent.change(screen.getByTestId('ia-pii-analizar-texto'), { target: { value: 'Mi cédula es 12345' } });
    await user.click(screen.getByTestId('ia-pii-analizar-submit'));
    await waitFor(() => expect(screen.getByTestId('ia-pii-detecciones')).toBeInTheDocument());
  });

  it('analizar error', async () => {
    api.detectarPiiIA.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await user.click(screen.getByTestId('ia-pii-analizar'));
    fireEvent.change(screen.getByTestId('ia-pii-analizar-texto'), { target: { value: 'x' } });
    await user.click(screen.getByTestId('ia-pii-analizar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('filtros disparan refetch', async () => {
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listAlertasPii).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('ia-pii-filter-estado'), { target: { value: 'pendiente' } });
    fireEvent.change(screen.getByTestId('ia-pii-filter-sev'), { target: { value: 'alta' } });
    await waitFor(() => expect(api.listAlertasPii).toHaveBeenCalledTimes(3));
  });

  it('refresh', async () => {
    const user = userEvent.setup();
    render(<DeteccionPII session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('ia-pii-table'));
    await user.click(screen.getByTestId('ia-pii-refresh'));
    expect(api.listAlertasPii).toHaveBeenCalledTimes(2);
  });
});
