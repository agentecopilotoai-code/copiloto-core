import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../services/adminSession.js', () => ({
  fetchAdminSession: vi.fn(),
  SESSION_UNAUTHORIZED: Symbol.for('SESSION_UNAUTHORIZED_FAKE'),
}));

// eslint-disable-next-line no-unused-vars
import { fetchAdminSession, SESSION_UNAUTHORIZED } from '../services/adminSession.js';
import { AuthProvider, useAuth } from './AuthContext.jsx';

function Probe() {
  const { isAuthenticated, isLoading, status, session, error, unauthorizedReason } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authed">{String(isAuthenticated)}</span>
      <span data-testid="email">{session?.profile?.email || ''}</span>
      <span data-testid="error">{error?.message || ''}</span>
      <span data-testid="reason">{unauthorizedReason || ''}</span>
    </div>
  );
}

beforeEach(() => {
  fetchAdminSession.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('<AuthProvider/>', () => {
  it('arranca en loading antes de resolver la sesión', () => {
    fetchAdminSession.mockReturnValue(new Promise(() => {}));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByTestId('status').textContent).toBe('loading');
    expect(screen.getByTestId('loading').textContent).toBe('true');
    expect(screen.getByTestId('authed').textContent).toBe('false');
  });

  it('marca authenticated cuando hay sesión', async () => {
    fetchAdminSession.mockResolvedValue({ profile: { email: 'a@b.co' } });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('authenticated');
    });
    expect(screen.getByTestId('authed').textContent).toBe('true');
    expect(screen.getByTestId('email').textContent).toBe('a@b.co');
  });

  it('marca anonymous cuando fetch retorna falsy', async () => {
    fetchAdminSession.mockResolvedValue(null);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('anonymous');
    });
    expect(screen.getByTestId('authed').textContent).toBe('false');
    expect(screen.getByTestId('reason').textContent).toBe('');
  });

  // M46 — sentinel SESSION_UNAUTHORIZED expone reason al frontend.
  it('marca anonymous + reason=session_expired cuando fetch devuelve sentinel', async () => {
    fetchAdminSession.mockResolvedValue({
      unauthorized: SESSION_UNAUTHORIZED,
      reason: 'session_expired',
    });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('anonymous');
    });
    expect(screen.getByTestId('reason').textContent).toBe('session_expired');
  });

  it('reason=no_session para 401 sin cookie', async () => {
    fetchAdminSession.mockResolvedValue({
      unauthorized: SESSION_UNAUTHORIZED,
      reason: 'no_session',
    });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('reason').textContent).toBe('no_session');
    });
  });

  it('expone error cuando el fetch falla', async () => {
    fetchAdminSession.mockRejectedValue(new Error('boom'));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('error');
    });
    expect(screen.getByTestId('error').textContent).toBe('boom');
  });
});

describe('useAuth()', () => {
  it('throws cuando se usa fuera del provider', () => {
    // Silence React error boundary noise.
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/useAuth/);
    errSpy.mockRestore();
  });
});
