import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
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
  it('pinta las filas de eventos transversales del core', () => {
    render(<AccountNotifications />);
    expect(screen.getByText('Alerta de seguridad')).toBeInTheDocument();
    expect(screen.getByText('Invitación a un negocio')).toBeInTheDocument();
    expect(screen.getByText('Cambio de rol')).toBeInTheDocument();
    expect(screen.getByText('Soporte ingresó a tu negocio')).toBeInTheDocument();
  });

  it('cada fila ofrece checkboxes para email/inapp', () => {
    render(<AccountNotifications />);
    const row = screen.getByText('Alerta de seguridad').closest('[role="row"]');
    expect(row).not.toBeNull();
    const checkboxes = within(row).getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
  });

  it('toggle de checkbox actualiza su estado checked', async () => {
    render(<AccountNotifications />);
    const checkbox = document.querySelector(
      'input[data-event="security_alert"][data-channel="email"]',
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
    expect(matrix).toEqual(
      expect.objectContaining({
        security_alert: expect.any(Object),
        tenant_invite: expect.any(Object),
        role_changed: expect.any(Object),
        support_mode_used: expect.any(Object),
      }),
    );
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalled();
    });
  });

  it('si el backend devuelve 422 muestra AlertBanner danger', async () => {
    const err = new Error('notification_matrix[bad][unknown]: channel must be one of email, inapp');
    err.status = 422;
    coreApi.patchMyNotifications.mockRejectedValueOnce(err);

    render(<AccountNotifications />);
    await userEvent.click(screen.getByRole('button', { name: /Guardar preferencias/ }));

    expect(await screen.findByText(/channel must be one of/)).toBeInTheDocument();
  });
});
