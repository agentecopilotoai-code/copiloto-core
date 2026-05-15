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

  /**
   * UI-023 — el `<header>` raíz aplica la clase `.header` del CSS module,
   * donde reside la regla `position: sticky`. jsdom no calcula layout real
   * (`getComputedStyle` no resuelve `position: sticky` de un module CSS), por
   * eso la prueba se queda en la capa estructural: confirmamos que el
   * elemento es `<header>` y recibe el className tokenizado.
   */
  it('uses a <header> element so the sticky CSS rule applies', () => {
    const { container } = render(<PageHeader title="Cualquier vista" />);
    const headerEl = container.querySelector('header');
    expect(headerEl).not.toBeNull();
    // CSS module hashes the class, so it suffices to check the attribute exists.
    expect(headerEl?.className).toBeTruthy();
  });
});
