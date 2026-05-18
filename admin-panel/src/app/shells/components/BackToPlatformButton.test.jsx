/**
 * BUG-015 — el botón "Volver a Platform" debe:
 *   1. Navegar a /platform al click.
 *   2. Mostrarse solo cuando el usuario tiene rol global (platform_owner)
 *      Y está bajo support_mode. Esto lo controla el padre (TenantShell)
 *      via `permissions.isSystemOwner` — este test solo cubre el rendering
 *      + navigation del componente.
 *   3. Usar texto/marcado accesible (botón con type="button" para no submit
 *      forms accidentalmente; title atribuído para tooltip).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

// eslint-disable-next-line import/first
import { BackToPlatformButton } from './BackToPlatformButton.jsx';

describe('BackToPlatformButton (BUG-015)', () => {
  it('renderiza el botón con type=button y label "← Platform"', () => {
    render(
      <MemoryRouter>
        <BackToPlatformButton />
      </MemoryRouter>,
    );
    const btn = screen.getByRole('button', { name: /Platform/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute('type', 'button');
    // El símbolo ← lo da contexto visual de "volver".
    expect(btn.textContent).toMatch(/Platform/);
  });

  it('al clickear navega a /platform', async () => {
    navigateMock.mockClear();
    render(
      <MemoryRouter>
        <BackToPlatformButton />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole('button', { name: /Platform/i }));
    expect(navigateMock).toHaveBeenCalledWith('/platform');
    expect(navigateMock).toHaveBeenCalledTimes(1);
  });

  it('tiene title atribuído para tooltip accesible', () => {
    render(
      <MemoryRouter>
        <BackToPlatformButton />
      </MemoryRouter>,
    );
    const btn = screen.getByRole('button', { name: /Platform/i });
    expect(btn).toHaveAttribute('title');
    // El title debe explicar qué hace el botón (tooltip on hover).
    expect(btn.getAttribute('title')).toMatch(/platform|cross-tenant/i);
  });
});
