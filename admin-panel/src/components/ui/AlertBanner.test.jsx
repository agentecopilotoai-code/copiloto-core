import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AlertBanner } from './AlertBanner.jsx';

describe('AlertBanner', () => {
  it('renders the title, description and action', () => {
    render(
      <AlertBanner tone="warning" title="Handoffs pendientes" action={<a href="/x">Ver</a>}>
        3 conversaciones esperan a un agente.
      </AlertBanner>,
    );
    expect(screen.getByText('Handoffs pendientes')).toBeInTheDocument();
    expect(screen.getByText('3 conversaciones esperan a un agente.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ver' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('falls back to the info tone for an unknown tone', () => {
    const { container } = render(<AlertBanner tone="explode" title="x" />);
    expect(container.firstChild.className).toMatch(/banner--info/);
  });

  it('applies the tone class', () => {
    const { container } = render(<AlertBanner tone="danger" title="x" />);
    expect(container.firstChild.className).toMatch(/banner--danger/);
  });
});
