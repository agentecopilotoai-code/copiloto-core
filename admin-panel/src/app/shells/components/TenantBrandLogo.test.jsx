import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { TenantBrandLogo } from './TenantBrandLogo.jsx';

describe('<TenantBrandLogo/>', () => {
  it('pinta iniciales del display_name', async () => {
    render(<TenantBrandLogo tenant={{ display_name: 'Burrito Bros', slug: 'burrito' }} />);
    const fallback = await screen.findByRole('img', { name: /Burrito Bros/ });
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback.textContent).toBe('BU');
  });

  it('usa `slug` si `display_name` está ausente', async () => {
    render(<TenantBrandLogo tenant={{ slug: 'taqueria' }} />);
    const fallback = await screen.findByRole('img', { name: /taqueria/ });
    expect(fallback.textContent).toBe('TA');
  });

  it('fallback genérico CO cuando tenant es null/undefined', async () => {
    render(<TenantBrandLogo tenant={null} />);
    const fallback = await screen.findByRole('img', { name: /Copiloto/ });
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback.textContent).toBe('CO');
  });

  it('strippea caracteres no alfanuméricos del slug antes de tomar las iniciales', async () => {
    render(<TenantBrandLogo tenant={{ slug: '--xy--corp' }} />);
    const fallback = await screen.findByRole('img', { name: /--xy--corp/ });
    expect(fallback.textContent).toBe('XY');
  });
});
