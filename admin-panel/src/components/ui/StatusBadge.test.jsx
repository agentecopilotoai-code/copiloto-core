import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge.jsx';

describe('StatusBadge', () => {
  it('renders the label', () => {
    render(<StatusBadge tone="success">Activo</StatusBadge>);
    expect(screen.getByText('Activo')).toBeInTheDocument();
  });

  it('applies tone class', () => {
    const { container } = render(<StatusBadge tone="danger">Error</StatusBadge>);
    expect(container.firstChild.className).toMatch(/badge--danger/);
  });

  it('falls back to neutral when tone is invalid', () => {
    const { container } = render(<StatusBadge tone="not-real">X</StatusBadge>);
    expect(container.firstChild.className).toMatch(/badge--neutral/);
  });
});
