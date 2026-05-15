import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ShellBottomNav } from './ShellBottomNav.jsx';

/**
 * UI-016.8 — Suite del bottom-nav móvil.
 *
 * Cobertura:
 *   - Render de slots primarios + ícono + label.
 *   - aria-current='page' en el activo.
 *   - Click dispara onModuleSelect con el id del módulo.
 *   - Cuando hay > 4 items, se colapsa el resto en "Más" (sheet).
 *   - La sheet expone los items overflow con role=dialog y aria-modal.
 *   - Items disabled se omiten del bottom-nav (el sidebar normal sí los
 *     pinta en "Sin acceso", pero la barra mobile solo muestra atajos
 *     navegables).
 *   - Sin grupos → no renderiza nada (null-safe).
 */

const fiveGroupNav = [
  {
    section: 'Inicio',
    items: [{ id: 'dashboard', label: 'Inicio', disabled: false }],
  },
  {
    section: 'Conversaciones',
    items: [
      { id: 'operations-desk', label: 'Inbox', disabled: false },
      { id: 'contacts', label: 'Contactos', disabled: false },
    ],
  },
  {
    section: 'Hoy',
    items: [{ id: 'appointments', label: 'Citas', disabled: false }],
  },
  {
    section: 'Negocio',
    items: [
      { id: 'analytics', label: 'Analítica', disabled: false },
      { id: 'services', label: 'Servicios', disabled: false },
      { id: 'branches', label: 'Sedes', disabled: false },
    ],
  },
];

describe('<ShellBottomNav/>', () => {
  it('renderiza un slot por cada destino primario (hasta 4) + "Más"', () => {
    render(
      <ShellBottomNav
        navGroups={fiveGroupNav}
        activeModuleId="dashboard"
        onModuleSelect={() => {}}
      />,
    );
    const nav = screen.getByRole('navigation', { name: 'Navegación móvil' });
    const buttons = within(nav).getAllByRole('button');
    // 4 primarios + 1 "Más" = 5 slots cuando hay > 4 items totales.
    expect(buttons).toHaveLength(5);
    expect(buttons[buttons.length - 1]).toHaveTextContent(/Más/);
  });

  it('marca el módulo activo con aria-current="page"', () => {
    render(
      <ShellBottomNav
        navGroups={fiveGroupNav}
        activeModuleId="operations-desk"
        onModuleSelect={() => {}}
      />,
    );
    const inbox = screen.getByRole('button', { name: /Inbox/ });
    expect(inbox).toHaveAttribute('aria-current', 'page');
  });

  it('dispara onModuleSelect con el id al clic en un slot primario', async () => {
    const onModuleSelect = vi.fn();
    render(
      <ShellBottomNav
        navGroups={fiveGroupNav}
        activeModuleId="dashboard"
        onModuleSelect={onModuleSelect}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /Citas/ }));
    expect(onModuleSelect).toHaveBeenCalledWith('appointments');
  });

  it('al pulsar "Más" abre una sheet con los items overflow', async () => {
    render(
      <ShellBottomNav
        navGroups={fiveGroupNav}
        activeModuleId="dashboard"
        onModuleSelect={() => {}}
      />,
    );
    const more = screen.getByRole('button', { name: /Más/ });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(more);
    expect(more).toHaveAttribute('aria-expanded', 'true');

    const sheet = screen.getByRole('dialog', { name: /Más módulos/ });
    expect(sheet).toHaveAttribute('aria-modal', 'true');
    // El 5º item (`analytics`) cae al overflow; los items 6 y 7 también
    // están en la sheet.
    expect(within(sheet).getByRole('button', { name: 'Analítica' })).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: 'Servicios' })).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: 'Sedes' })).toBeInTheDocument();
  });

  it('al seleccionar un overflow item dispara onModuleSelect y cierra la sheet', async () => {
    const onModuleSelect = vi.fn();
    render(
      <ShellBottomNav
        navGroups={fiveGroupNav}
        activeModuleId="dashboard"
        onModuleSelect={onModuleSelect}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /Más/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Servicios' }));
    expect(onModuleSelect).toHaveBeenCalledWith('services');
    // Sheet cerrada.
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('omite items deshabilitados (el sidebar normal los muestra como "Sin acceso")', () => {
    const navWithDisabled = [
      {
        section: 'Inicio',
        items: [
          { id: 'dashboard', label: 'Inicio', disabled: false },
          { id: 'denied', label: 'Sin acceso', disabled: true },
        ],
      },
    ];
    render(
      <ShellBottomNav
        navGroups={navWithDisabled}
        activeModuleId="dashboard"
        onModuleSelect={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /Sin acceso/ })).toBeNull();
  });

  it('cuando no hay navGroups no renderiza nada (null-safe)', () => {
    const { container } = render(
      <ShellBottomNav navGroups={[]} activeModuleId="x" onModuleSelect={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('con ≤ 4 items totales no muestra el botón "Más"', () => {
    const small = [
      {
        section: 'Inicio',
        items: [
          { id: 'dashboard', label: 'Inicio', disabled: false },
          { id: 'operations-desk', label: 'Inbox', disabled: false },
        ],
      },
    ];
    render(
      <ShellBottomNav
        navGroups={small}
        activeModuleId="dashboard"
        onModuleSelect={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: /Más/ })).toBeNull();
  });
});
