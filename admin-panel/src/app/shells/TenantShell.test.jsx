import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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

describe('<TenantShell/>', () => {
  it('pinta sidebar agrupada, topbar y children', () => {
    render(
      <TenantShell {...baseProps}>
        <p>contenido del módulo</p>
      </TenantShell>,
    );
    expect(screen.getByRole('heading', { name: 'Servicios' })).toBeInTheDocument();
    expect(screen.getByText('contenido del módulo')).toBeInTheDocument();
    expect(screen.getByText('Negocio')).toBeInTheDocument();
    expect(screen.getByText('Camila Rojas')).toBeInTheDocument();
  });

  it('marca el módulo activo con aria-current', () => {
    render(
      <TenantShell {...baseProps}>
        <p>x</p>
      </TenantShell>,
    );
    expect(screen.getByRole('button', { name: 'Servicios' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('dispara onModuleSelect al click en un item de navegación', async () => {
    const onModuleSelect = vi.fn();
    render(
      <TenantShell {...baseProps} onModuleSelect={onModuleSelect}>
        <p>x</p>
      </TenantShell>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Contactos' }));
    expect(onModuleSelect).toHaveBeenCalledWith('contacts');
  });

  it('el tenant switcher queda deshabilitado con un solo tenant', () => {
    render(
      <TenantShell {...baseProps}>
        <p>x</p>
      </TenantShell>,
    );
    expect(screen.getByRole('button', { name: /Acme/ })).toBeDisabled();
  });
});
