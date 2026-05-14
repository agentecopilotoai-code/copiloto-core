import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmptyState } from './EmptyState.jsx';

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(<EmptyState title="Vacío" description="No hay datos." />);
    expect(screen.getByRole('heading', { name: 'Vacío' })).toBeInTheDocument();
    expect(screen.getByText('No hay datos.')).toBeInTheDocument();
  });

  it('renders an action', () => {
    render(<EmptyState title="Sin datos" action={<button type="button">Crear</button>} />);
    expect(screen.getByRole('button', { name: 'Crear' })).toBeInTheDocument();
  });
});
