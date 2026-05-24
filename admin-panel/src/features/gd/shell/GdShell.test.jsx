import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { GdShell } from './GdShell.jsx';

describe('GdShell', () => {
  beforeEach(() => window.localStorage.clear());

  it('renderiza wrapper data-testid + children', () => {
    render(
      <GdShell roles={['gd.radicador']}>
        <div data-testid="child">Hola</div>
      </GdShell>,
    );
    expect(screen.getByTestId('gd-shell-root')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('renderiza breadcrumbs cuando se pasan', () => {
    render(
      <GdShell
        roles={['gd.radicador']}
        breadcrumbs={[
          { label: 'Inicio', path: '/gd' },
          { label: 'Ventanilla' },
        ]}
      >
        <p>x</p>
      </GdShell>,
    );
    expect(screen.getByText('Inicio')).toBeInTheDocument();
    expect(screen.getByText('Ventanilla')).toBeInTheDocument();
  });

  it('breadcrumb click dispara onNavigate al path', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <GdShell
        roles={['gd.radicador']}
        onNavigate={onNavigate}
        breadcrumbs={[
          { label: 'Inicio', path: '/gd' },
          { label: 'Ventanilla' },
        ]}
      >
        <p>x</p>
      </GdShell>,
    );
    await user.click(screen.getByText('Inicio'));
    expect(onNavigate).toHaveBeenCalledWith('/gd');
  });

  it('último breadcrumb es "here" (no link)', () => {
    const { container } = render(
      <GdShell
        roles={['gd.radicador']}
        breadcrumbs={[{ label: 'A' }, { label: 'B' }]}
      >
        <p />
      </GdShell>,
    );
    expect(container.querySelector('.here')).toBeTruthy();
  });

  it('data-scope refleja el scope inicial', () => {
    render(
      <GdShell roles={['gd.radicador']} tenantSlug="acme">
        <p />
      </GdShell>,
    );
    expect(screen.getByTestId('gd-shell-root').getAttribute('data-scope')).toBe('propio');
  });
});
