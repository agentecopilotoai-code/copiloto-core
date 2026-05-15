import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// UI-016.7-FU — mock the auth/session source so the hydration effect can run.
let mockSession;
vi.mock('../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

vi.mock('../../services/coreApi.js', () => ({
  getMyNotifications: vi.fn(),
  patchMyNotifications: vi.fn(),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('../../components/ui/index.js', async () => {
  const actual = await vi.importActual('../../components/ui/index.js');
  return {
    ...actual,
    useToast: () => ({
      push: () => '',
      dismiss: () => {},
      success: toastSuccess,
      error: toastError,
      info: () => '',
      warning: () => '',
    }),
  };
});

// eslint-disable-next-line import/first
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { AccountNotifications } from './AccountNotifications.jsx';

const SESSION = { accessToken: 'tok', profile: { sub: 'u-1' } };

beforeEach(() => {
  mockSession = SESSION;
  toastSuccess.mockClear();
  toastError.mockClear();
  coreApi.getMyNotifications.mockReset();
  coreApi.patchMyNotifications.mockReset();
  coreApi.getMyNotifications.mockResolvedValue({
    user_id: 'u-1',
    notification_matrix: {},
  });
  coreApi.patchMyNotifications.mockResolvedValue({ user_id: 'u-1' });
});

describe('<AccountNotifications/>', () => {
  it('pinta las 6 filas de eventos del HTML T3', () => {
    render(<AccountNotifications />);
    expect(screen.getByText('Digest diario')).toBeInTheDocument();
    expect(screen.getByText('Handoff con SLA cercano')).toBeInTheDocument();
    expect(screen.getByText('Cobro fallido')).toBeInTheDocument();
    expect(screen.getByText('Cita confirmada')).toBeInTheDocument();
    expect(screen.getByText('Quality rating de WhatsApp baja')).toBeInTheDocument();
    expect(screen.getByText('Resumen semanal de campañas')).toBeInTheDocument();
  });

  it('cada fila ofrece checkboxes para email/wa/inapp', () => {
    render(<AccountNotifications />);
    const dailyDigestRow = screen.getByText('Digest diario').closest('[role="row"]');
    expect(dailyDigestRow).not.toBeNull();
    const checkboxes = within(dailyDigestRow).getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3);
  });

  it('toggle de checkbox actualiza su estado checked', async () => {
    render(<AccountNotifications />);
    const checkbox = document.querySelector(
      'input[data-event="daily_digest"][data-channel="email"]',
    );
    expect(checkbox).toBeChecked();
    await userEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it('al guardar invoca patchMyNotifications con la matriz y dispara toast success', async () => {
    render(<AccountNotifications />);
    await userEvent.click(screen.getByRole('button', { name: /Guardar preferencias/ }));
    await waitFor(() => {
      expect(coreApi.patchMyNotifications).toHaveBeenCalledTimes(1);
    });
    const [, matrix] = coreApi.patchMyNotifications.mock.calls[0];
    // The 6 canonical event ids must appear in the payload.
    expect(matrix).toEqual(
      expect.objectContaining({
        daily_digest: expect.any(Object),
        handoff_sla: expect.any(Object),
        payment_failed: expect.any(Object),
        appointment_confirmed: expect.any(Object),
        quality_rating_low: expect.any(Object),
        weekly_campaigns_summary: expect.any(Object),
      }),
    );
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalled();
    });
  });

  it('si el backend devuelve 422 muestra AlertBanner danger', async () => {
    const err = new Error('notification_matrix[bad][unknown]: channel must be one of email, wa, inapp');
    err.status = 422;
    coreApi.patchMyNotifications.mockRejectedValueOnce(err);

    render(<AccountNotifications />);
    await userEvent.click(screen.getByRole('button', { name: /Guardar preferencias/ }));

    expect(
      await screen.findByText(/channel must be one of/),
    ).toBeInTheDocument();
  });
});
