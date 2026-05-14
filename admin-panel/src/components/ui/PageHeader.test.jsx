import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PageHeader } from './PageHeader.jsx';

describe('PageHeader', () => {
  it('renders eyebrow, title, description and actions', () => {
    render(
      <PageHeader
        eyebrow="Platform"
        title="Fleet · Tenants"
        description="Vista flota"
        actions={<button type="button">Crear</button>}
      />,
    );
    expect(screen.getByText('Platform')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Fleet · Tenants' })).toBeInTheDocument();
    expect(screen.getByText('Vista flota')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crear' })).toBeInTheDocument();
  });
});
