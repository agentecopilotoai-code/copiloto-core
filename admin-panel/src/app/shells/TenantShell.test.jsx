import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { adminModules } from '../modules.js';
import { TenantShell } from './TenantShell.jsx';

const baseProps = {
  profile: { name: 'Camila Rojas', roles: ['owner'] },
  permissions: { role: 'owner', can: () => true },
  modules: adminModules,
  activeModule: { id: 'services', label: 'Servicios' },
  activeModuleId: 'services',
  onModuleSelect: () => {},
  tenantOptions: [{ id: 't1', slug: 'acme', display_name: 'Acme', role: 'owner' }],
  activeTenantId: 't1',
  onTenantChange: () => {},
  canSwitchTenants: false,
};

function renderShell(children, props = {}) {
  return render(
    <MemoryRouter>
      <TenantShell {...baseProps} {...props}>
        {children}
      </TenantShell>
    </MemoryRouter>,
  );
}

describe('<TenantShell/>', () => {
  it('pinta sidebar agrupada, topbar y children', () => {
    renderShell(<p>contenido del módulo</p>);
    expect(screen.getByRole('heading', { name: 'Servicios' })).toBeInTheDocument();
    expect(screen.getByText('contenido del módulo')).toBeInTheDocument();
    expect(screen.getByText('Negocio')).toBeInTheDocument();
    expect(screen.getByText('Camila Rojas')).toBeInTheDocument();
  });

  it('marca el módulo activo con aria-current', () => {
    renderShell(<p>x</p>);
    expect(screen.getByRole('button', { name: 'Servicios' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('dispara onModuleSelect al click en un item de navegación', async () => {
    const onModuleSelect = vi.fn();
    renderShell(<p>x</p>, { onModuleSelect });
    await userEvent.click(screen.getByRole('button', { name: 'Contactos' }));
    expect(onModuleSelect).toHaveBeenCalledWith('contacts');
  });

  it('el tenant switcher queda deshabilitado con un solo tenant', () => {
    renderShell(<p>x</p>);
    expect(screen.getByRole('button', { name: /Acme/ })).toBeDisabled();
  });

  it('UI-016.7 — la tarjeta de usuario expone un link a /account/profile', () => {
    renderShell(<p>x</p>);
    const accountLink = screen.getByRole('link', {
      name: /Abrir mi cuenta \(Camila Rojas\)/,
    });
    expect(accountLink).toHaveAttribute('href', '/account/profile');
  });

  it('BUG-015 — owner regular NO ve el botón "Volver a Platform"', () => {
    // baseProps.permissions = { role: 'owner', can: () => true } sin
    // isSystemOwner — el dueño del tenant NO debe ver el botón (no tiene
    // a dónde volver, su home es el tenant mismo).
    renderShell(<p>x</p>);
    expect(
      screen.queryByRole('button', { name: /Platform/i }),
    ).not.toBeInTheDocument();
  });

  it('BUG-015 — platform_owner bajo support_mode SÍ ve el botón "Volver a Platform"', () => {
    // Caso de uso: platform_owner activó support_mode contra el tenant
    // (via "Ver como tenant" o creando un tenant nuevo donde es owner).
    // `isSystemOwner=true` es el flag que el padre usa para mostrar el
    // botón — el componente confía en ese gate.
    renderShell(<p>x</p>, {
      permissions: {
        role: 'platform_owner',
        can: () => true,
        isSystemOwner: true,
      },
    });
    const btn = screen.getByRole('button', { name: /Platform/i });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveAttribute('type', 'button');
  });

  it('BUG-015 — isSystemOwner=false explícito tampoco monta el botón', () => {
    // Defensive: solo el flag verdadero monta el botón. Cualquier otro
    // valor (false, undefined dentro de permissions) lo oculta. Esto
    // refleja la intent del fix: el botón es EXCLUSIVO para platform_owners
    // bajo support_mode.
    renderShell(<p>x</p>, {
      permissions: {
        role: 'owner',
        can: () => true,
        isSystemOwner: false,
      },
    });
    expect(
      screen.queryByRole('button', { name: /Platform/i }),
    ).not.toBeInTheDocument();
  });
});
