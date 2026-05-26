import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PublicLanding } from './PublicLanding.jsx';

// M46 — PublicLanding ahora depende de `useAuth().unauthorizedReason`.
// Mockeamos el hook para controlar el reason por test.
vi.mock('../../context/AuthContext.jsx', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../../context/AuthContext.jsx';

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
});
