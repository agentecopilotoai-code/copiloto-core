import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PublicLanding } from './PublicLanding.jsx';

describe('<PublicLanding/>', () => {
  it('renderiza el título Copiloto Core', () => {
    render(<PublicLanding />);
    expect(screen.getByRole('heading', { name: /Copiloto Core/i })).toBeInTheDocument();
  });

  it('renderiza el CTA de login con href al endpoint del BFF', () => {
    render(<PublicLanding />);
    const cta = screen.getByTestId('public-landing-login');
    expect(cta).toBeInTheDocument();
    expect(cta.getAttribute('href')).toContain('/admin/login');
  });

  it('describe el sistema en el subtítulo', () => {
    render(<PublicLanding />);
    expect(screen.getByText(/Sistema operativo multi-tenant/i)).toBeInTheDocument();
  });
});
