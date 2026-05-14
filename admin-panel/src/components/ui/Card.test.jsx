import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Card, CardHeader, CardBody, CardFooter } from './Card.jsx';

describe('Card', () => {
  it('renders title and body', () => {
    render(
      <Card>
        <CardHeader title="Resumen" subtitle="Últimos 7 días" />
        <CardBody>contenido</CardBody>
        <CardFooter>pie</CardFooter>
      </Card>,
    );
    expect(screen.getByRole('heading', { name: 'Resumen' })).toBeInTheDocument();
    expect(screen.getByText('Últimos 7 días')).toBeInTheDocument();
    expect(screen.getByText('contenido')).toBeInTheDocument();
    expect(screen.getByText('pie')).toBeInTheDocument();
  });

  it('applies alt tone class', () => {
    const { container } = render(<Card tone="alt">x</Card>);
    expect(container.firstChild.className).toMatch(/card--alt/);
  });
});
