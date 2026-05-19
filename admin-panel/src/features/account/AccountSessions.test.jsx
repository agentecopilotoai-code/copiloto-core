import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// UI-016.7-FU — mock auth/session source so the GET hydration effect runs.
let mockSession;
vi.mock('../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

vi.mock('../../services/coreApi.js', () => ({
  listMySessions: vi.fn(),
  revokeMySession: vi.fn(),
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
import { AccountSessions } from './AccountSessions.jsx';

const SESSION = { accessToken: 'tok', profile: { sub: 'u-1' } };

beforeEach(() => {
  mockSession = SESSION;
  toastSuccess.mockClear();
  toastError.mockClear();
  coreApi.listMySessions.mockReset();
  coreApi.revokeMySession.mockReset();
  coreApi.listMySessions.mockResolvedValue({
    user_id: 'u-1',
    sessions: [{ id: 'current', current: true, last_seen_at: null }],
    follow_up: 'UI-016.7-FU-SESSIONS',
  });
  coreApi.revokeMySession.mockResolvedValue(null);
});

describe('<AccountSessions/>', () => {
  it('pinta heading + listado de sesiones demo', () => {
    render(<AccountSessions />);
    expect(screen.getByRole('heading', { name: 'Sesiones activas' })).toBeInTheDocument();
    expect(screen.getByText(/Chrome 124 · macOS/)).toBeInTheDocument();
    expect(screen.getByText(/WhatsApp Web · iPhone 15/)).toBeInTheDocument();
    expect(screen.getByText(/Firefox 125 · Ubuntu/)).toBeInTheDocument();
  });

  it('marca la sesión actual con el chip "esta sesión"', () => {
    render(<AccountSessions />);
    expect(screen.getByText('esta sesión')).toBeInTheDocument();
  });

  it('botón "Revocar" de la sesión actual queda deshabilitado', () => {
    render(<AccountSessions />);
    const buttons = screen.getAllByRole('button', { name: /Revocar sesión/ });
    const currentBtn = buttons.find((btn) =>
      btn.getAttribute('aria-label')?.includes('Chrome 124'),
    );
    expect(currentBtn).toBeDisabled();
  });

  it('al montar invoca listMySessions para refrescar el estado', async () => {
    render(<AccountSessions />);
    await waitFor(() => {
      expect(coreApi.listMySessions).toHaveBeenCalledTimes(1);
    });
  });

  it('revocar otra sesión muestra AlertBanner explicando workaround (BUG-233)', async () => {
    render(<AccountSessions />);
    const otherSessionBtn = screen
      .getAllByRole('button', { name: /Revocar sesión/ })
      .find((btn) => btn.getAttribute('aria-label')?.includes('WhatsApp Web'));
    await userEvent.click(otherSessionBtn);
    // BUG-233 (codex P2 sobre PR #16): el copy original exponia el endpoint
    // `DELETE /v1/me/sessions` y el codigo interno UI-016.7-FU-SESSIONS,
    // jerga tecnica visible al usuario. Ahora el banner describe el
    // workaround en lenguaje de negocio.
    expect(
      screen.getByText(/cambiá tu contraseña/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/cerrar la sesión actual desde acá/i),
    ).toBeInTheDocument();
    // No HTTP call para otras sesiones — el backend retorna 404 hasta que
    // exista el session store.
    expect(coreApi.revokeMySession).not.toHaveBeenCalled();
  });

  it('al cerrar todas las demás sesiones muestra AlertBanner UI-016.7-FU-SESSIONS', async () => {
    render(<AccountSessions />);
    await userEvent.click(
      screen.getByRole('button', { name: 'Cerrar todas las demás sesiones' }),
    );
    expect(screen.getByText(/Cerrar otras sesiones queda en standby/)).toBeInTheDocument();
  });
});
