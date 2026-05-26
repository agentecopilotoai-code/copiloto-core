import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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

const REAL_ITEMS = [
  {
    id: 'sess-current',
    device: 'Chrome 124 · macOS',
    location: 'Bogotá, Colombia',
    last_seen_at: '2026-05-25T10:00:00Z',
    current: true,
  },
  {
    id: 'sess-old',
    device: 'Firefox · Ubuntu',
    location: 'Medellín',
    last_seen_at: '2026-05-23T08:00:00Z',
    current: false,
  },
];

beforeEach(() => {
  mockSession = SESSION;
  toastSuccess.mockClear();
  toastError.mockClear();
  coreApi.listMySessions.mockReset();
  coreApi.revokeMySession.mockReset();
  coreApi.listMySessions.mockResolvedValue({ items: REAL_ITEMS });
  coreApi.revokeMySession.mockResolvedValue(null);
});

describe('<AccountSessions/>', () => {
  it('pinta el heading + las sesiones reales devueltas por el backend', async () => {
    render(<AccountSessions />);
    expect(screen.getByRole('heading', { name: 'Sesiones activas' })).toBeInTheDocument();
    expect(await screen.findByText('Chrome 124 · macOS')).toBeInTheDocument();
    expect(screen.getByText('Firefox · Ubuntu')).toBeInTheDocument();
  });

  it('marca la sesión actual con el chip "esta sesión"', async () => {
    render(<AccountSessions />);
    expect(await screen.findByText('esta sesión')).toBeInTheDocument();
  });

  it('botón "Revocar" de la sesión actual queda deshabilitado', async () => {
    render(<AccountSessions />);
    await screen.findByText('Chrome 124 · macOS');
    const buttons = screen.getAllByRole('button', { name: /Revocar sesión/ });
    const currentBtn = buttons.find((btn) =>
      btn.getAttribute('aria-label')?.includes('Chrome 124'),
    );
    expect(currentBtn).toBeDisabled();
  });

  it('al montar invoca listMySessions', async () => {
    render(<AccountSessions />);
    await waitFor(() => {
      expect(coreApi.listMySessions).toHaveBeenCalledTimes(1);
    });
  });

  it('revoke de otra sesión llama al backend + refresca', async () => {
    render(<AccountSessions />);
    await screen.findByText('Firefox · Ubuntu');
    const buttons = screen.getAllByRole('button', { name: /Revocar sesión/ });
    const otherBtn = buttons.find((btn) =>
      btn.getAttribute('aria-label')?.includes('Firefox'),
    );
    await userEvent.click(otherBtn);
    await waitFor(() => {
      expect(coreApi.revokeMySession).toHaveBeenCalledWith(SESSION, 'sess-old');
    });
  });

  it('revoke failure dispara toast error', async () => {
    coreApi.revokeMySession.mockRejectedValue(new Error('nope'));
    render(<AccountSessions />);
    await screen.findByText('Firefox · Ubuntu');
    const otherBtn = screen
      .getAllByRole('button', { name: /Revocar sesión/ })
      .find((btn) => btn.getAttribute('aria-label')?.includes('Firefox'));
    await userEvent.click(otherBtn);
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('nope');
    });
  });

  it('empty state cuando el backend devuelve items vacíos', async () => {
    coreApi.listMySessions.mockResolvedValue({ items: [] });
    render(<AccountSessions />);
    expect(await screen.findByText(/Sin sesiones registradas/i)).toBeInTheDocument();
  });

  it('error path muestra alert banner', async () => {
    coreApi.listMySessions.mockRejectedValue(new Error('boom'));
    render(<AccountSessions />);
    expect(await screen.findByText(/No se pudieron cargar/i)).toBeInTheDocument();
  });

  it('no dispara listMySessions si no hay session', () => {
    mockSession = null;
    render(<AccountSessions />);
    expect(coreApi.listMySessions).not.toHaveBeenCalled();
  });
});
