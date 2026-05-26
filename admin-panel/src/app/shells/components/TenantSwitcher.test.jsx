import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TenantSwitcher } from './TenantSwitcher.jsx';

const tenants = [
  { id: 't1', slug: 'acme', display_name: 'Acme', role: 'owner' },
  { id: 't2', slug: 'beta-corp', display_name: 'Beta Corp', roles: ['admin'] },
  { id: 't3', slug: '--gamma--', label: 'gamma label' },
];

describe('<TenantSwitcher/>', () => {
  it('devuelve null si no hay tenants', () => {
    const { container } = render(
      <TenantSwitcher tenantOptions={[]} onTenantChange={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('pinta tenant activo y deshabilita trigger sin switch', () => {
    render(
      <TenantSwitcher
        tenantOptions={tenants}
        activeTenantId="t1"
        canSwitchTenants={false}
        onTenantChange={() => {}}
      />,
    );
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('cae al primer tenant cuando el activeTenantId no matchea', () => {
    render(
      <TenantSwitcher
        tenantOptions={tenants}
        activeTenantId="missing"
        canSwitchTenants
        onTenantChange={() => {}}
      />,
    );
    expect(screen.getByText('Acme')).toBeInTheDocument();
  });

  it('abre/cierra el menú con canSwitchTenants', async () => {
    render(
      <TenantSwitcher
        tenantOptions={tenants}
        activeTenantId="t1"
        canSwitchTenants
        onTenantChange={() => {}}
      />,
    );
    const trigger = screen.getByRole('button');
    await userEvent.click(trigger);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('Tus tenants')).toBeInTheDocument();
    await userEvent.click(trigger);
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('selecciona otro tenant y dispara onTenantChange', async () => {
    const onTenantChange = vi.fn();
    render(
      <TenantSwitcher
        tenantOptions={tenants}
        activeTenantId="t1"
        canSwitchTenants
        onTenantChange={onTenantChange}
      />,
    );
    await userEvent.click(screen.getByRole('button'));
    await userEvent.click(screen.getByRole('option', { name: /Beta Corp/ }));
    expect(onTenantChange).toHaveBeenCalledWith('t2');
  });

  it('cierra el menú al click fuera del wrapper', async () => {
    render(
      <div>
        <TenantSwitcher
          tenantOptions={tenants}
          activeTenantId="t1"
          canSwitchTenants
          onTenantChange={() => {}}
        />
        <button type="button" data-testid="outside">x</button>
      </div>,
    );
    await userEvent.click(screen.getByRole('button', { name: /Acme/ }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('outside'));
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('renderiza initials defensivos para slug con caracteres no alfanuméricos', () => {
    render(
      <TenantSwitcher
        tenantOptions={[{ id: 'x', slug: '---' }]}
        activeTenantId="x"
        canSwitchTenants={false}
        onTenantChange={() => {}}
      />,
    );
    // initials cae al fallback 'T' cuando no quedan chars válidos.
    expect(screen.getByText('T', { selector: '.tenantAvatar' })).toBeInTheDocument();
  });
});
