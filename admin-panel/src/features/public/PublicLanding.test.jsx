import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PublicLanding } from './PublicLanding.jsx';

// M46 — PublicLanding ahora depende de `useAuth().unauthorizedReason`.
// Mockeamos el hook para controlar el reason por test.
vi.mock('../../context/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../../context/AuthContext.jsx';

// M56 — el componente lee `?login_error=...` de window.location. jsdom
// resetea el search entre tests pero hay que setearlo explícito.
function setLoginError(value) {
  const url = new URL('http://localhost:3000/admin/');
  if (value) url.searchParams.set('login_error', value);
  window.history.replaceState({}, '', url);
}

beforeEach(() => {
  setLoginError(null);  // arranca limpio
});
afterEach(() => {
  setLoginError(null);  // limpia para no leakear entre tests
});

describe('<PublicLanding/>', () => {
  it('renderiza el título Copiloto Core', () => {
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    expect(screen.getByRole('heading', { name: /Copiloto Core/i })).toBeInTheDocument();
  });

  it('renderiza el CTA de login con href al endpoint del BFF', () => {
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    const cta = screen.getByTestId('public-landing-login');
    expect(cta).toBeInTheDocument();
    expect(cta.getAttribute('href')).toContain('/admin/login');
  });

  it('describe el sistema en el subtítulo cuando no hay sesión previa', () => {
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    expect(screen.getByText(/Sistema operativo multi-tenant/i)).toBeInTheDocument();
    // No banner de "tu sesión expiró"
    expect(screen.queryByTestId('public-landing-session-expired')).toBeNull();
  });

  it('describe el sistema cuando reason=no_session (user nuevo)', () => {
    useAuth.mockReturnValue({ unauthorizedReason: 'no_session' });
    render(<PublicLanding />);
    expect(screen.getByText(/Sistema operativo multi-tenant/i)).toBeInTheDocument();
    expect(screen.queryByTestId('public-landing-session-expired')).toBeNull();
  });

  it('muestra banner explicativo cuando reason=session_expired', () => {
    useAuth.mockReturnValue({ unauthorizedReason: 'session_expired' });
    render(<PublicLanding />);
    const banner = screen.getByTestId('public-landing-session-expired');
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toMatch(/Tu sesión expiró/i);
    // El CTA cambia de label cuando hay sesión expirada
    const cta = screen.getByTestId('public-landing-login');
    expect(cta.textContent).toMatch(/Volver a iniciar sesión/i);
    // El subtitle genérico NO se renderiza (es exclusivo del banner).
    expect(screen.queryByText(/Sistema operativo multi-tenant/i)).toBeNull();
  });

  // M56 — query param ?login_error=... del BFF tras callback OAuth fallido.
  it('muestra banner state_missing cuando ?login_error=state_missing', () => {
    setLoginError('state_missing');
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    const banner = screen.getByTestId('public-landing-session-expired');
    expect(banner.textContent).toMatch(/flujo de login expiró/i);
    expect(banner.textContent).toMatch(/recargaste el URL/i);
  });

  it('muestra banner state_mismatch (pestañas múltiples)', () => {
    setLoginError('state_mismatch');
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    expect(screen.getByTestId('public-landing-session-expired').textContent)
      .toMatch(/varias pestañas/i);
  });

  it('muestra banner state_expired', () => {
    setLoginError('state_expired');
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    expect(screen.getByTestId('public-landing-session-expired').textContent)
      .toMatch(/Tardaste más de 10 minutos/i);
  });

  it('muestra banner auth0_access_denied (user canceló)', () => {
    setLoginError('auth0_access_denied');
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    expect(screen.getByTestId('public-landing-session-expired').textContent)
      .toMatch(/Cancelaste el login/i);
  });

  it('muestra banner genérico para login_error desconocido', () => {
    setLoginError('unexpected_value_xyz');
    useAuth.mockReturnValue({ unauthorizedReason: null });
    render(<PublicLanding />);
    const banner = screen.getByTestId('public-landing-session-expired');
    expect(banner.textContent).toMatch(/Hubo un problema con el login/i);
    expect(banner.textContent).toMatch(/unexpected_value_xyz/);
  });

  it('login_error tiene PRIORIDAD sobre session_expired', () => {
    // Si vienen ambos contextos a la vez (el SPA tenía cookie zombie Y
    // el OAuth falló), priorizamos el contexto MÁS RECIENTE (callback fail).
    setLoginError('state_missing');
    useAuth.mockReturnValue({ unauthorizedReason: 'session_expired' });
    render(<PublicLanding />);
    const banner = screen.getByTestId('public-landing-session-expired');
    expect(banner.textContent).toMatch(/flujo de login expiró/i);
    expect(banner.textContent).not.toMatch(/Tu sesión expiró/i);
  });
});
