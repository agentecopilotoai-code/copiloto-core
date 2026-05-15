import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

let mockSession;
vi.mock('../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

// UI-016.7-FU — mock the coreApi helpers so the test runs without touching
// the network. The component calls `getMyProfile` on mount (best-effort
// hydration) and `patchMyProfile` on submit.
vi.mock('../../services/coreApi.js', () => ({
  getMyProfile: vi.fn(),
  patchMyProfile: vi.fn(),
}));

// UI-016.7-FU — stub `useToast` so the toast pattern (UI-016.5) does not
// require mounting the global <ToastProvider/>. We capture calls so we can
// assert success/error feedback.
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
import { AccountProfile } from './AccountProfile.jsx';

const OWNER_PROFILE = {
  name: 'Camila Rojas Martínez',
  email: 'camila@clinicaen.co',
  phone_number: '+57 300 8842 100',
  roles: ['owner'],
};

const SESSION = { accessToken: 'tok', profile: OWNER_PROFILE };

beforeEach(() => {
  mockSession = SESSION;
  toastSuccess.mockClear();
  toastError.mockClear();
  coreApi.getMyProfile.mockReset();
  coreApi.patchMyProfile.mockReset();
  coreApi.getMyProfile.mockResolvedValue({
    user_id: 'u-1',
    email: OWNER_PROFILE.email,
    display_name: OWNER_PROFILE.name,
    phone: OWNER_PROFILE.phone_number,
    locale: 'es-CO',
    timezone: 'America/Bogota',
    theme_override: null,
    auth0_synced_at: null,
    mfa_enabled: false,
    last_login_at: null,
  });
  coreApi.patchMyProfile.mockResolvedValue({ user_id: 'u-1' });
});

describe('<AccountProfile/>', () => {
  it('pinta hero con nombre, email del profile y badge del rol', () => {
    render(<AccountProfile />);
    expect(screen.getByRole('heading', { name: 'Perfil' })).toBeInTheDocument();
    expect(screen.getByText('Camila Rojas Martínez')).toBeInTheDocument();
    expect(screen.getByText(/camila@clinicaen.co/)).toBeInTheDocument();
    expect(screen.getByText('owner')).toBeInTheDocument();
  });

  it('email es read-only y muestra el helper de Auth0', () => {
    render(<AccountProfile />);
    const emailInput = screen.getByLabelText(/Email/);
    expect(emailInput).toHaveAttribute('readOnly');
    expect(screen.getByText(/Lo gestiona Auth0/)).toBeInTheDocument();
  });

  it('al guardar invoca patchMyProfile con el payload del form y muestra toast success', async () => {
    render(<AccountProfile />);
    await userEvent.click(screen.getByRole('button', { name: /Guardar cambios/ }));
    await waitFor(() => {
      expect(coreApi.patchMyProfile).toHaveBeenCalledTimes(1);
    });
    const [, payload] = coreApi.patchMyProfile.mock.calls[0];
    expect(payload).toMatchObject({
      display_name: 'Camila Rojas Martínez',
      locale: 'es-CO',
      timezone: 'America/Bogota',
    });
    await waitFor(() => {
      expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('Perfil'));
    });
  });

  it('si el backend devuelve 422 muestra AlertBanner danger con el detail', async () => {
    const err = new Error('display_name must be a string ≤ 200 chars');
    err.status = 422;
    coreApi.patchMyProfile.mockRejectedValueOnce(err);

    render(<AccountProfile />);
    await userEvent.click(screen.getByRole('button', { name: /Guardar cambios/ }));

    expect(
      await screen.findByText(/display_name must be a string/),
    ).toBeInTheDocument();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('si el backend devuelve 500 dispara toast.error', async () => {
    const err = new Error('Internal Server Error');
    err.status = 500;
    coreApi.patchMyProfile.mockRejectedValueOnce(err);

    render(<AccountProfile />);
    await userEvent.click(screen.getByRole('button', { name: /Guardar cambios/ }));

    await waitFor(() => {
      expect(toastError).toHaveBeenCalled();
    });
  });

  it('permite editar el nombre antes de guardar', async () => {
    render(<AccountProfile />);
    const nameInput = screen.getByLabelText('Nombre completo');
    // Esperar a que el effect de hidratación (getMyProfile) se asiente
    // antes de manipular el input — sino el set del effect compite con el
    // userEvent.clear() y el campo termina concatenado.
    await waitFor(() => expect(coreApi.getMyProfile).toHaveBeenCalled());
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'Camila R.');
    expect(nameInput).toHaveValue('Camila R.');
  });

  it('si no hay session.profile usa fallback "Usuario" sin reventar', () => {
    mockSession = null;
    render(<AccountProfile />);
    expect(screen.getByText('Usuario')).toBeInTheDocument();
  });
});
