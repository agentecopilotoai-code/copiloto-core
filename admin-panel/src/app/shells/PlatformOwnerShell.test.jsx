import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { adminModules } from '../../data/modules.js';
import { PlatformOwnerShell } from './PlatformOwnerShell.jsx';

const baseProps = {
  profile: { name: 'Mariana Ortiz', roles: ['platform_owner'] },
  permissions: { role: 'platform_owner', can: () => true },
  modules: adminModules,
  activeModule: { id: 'platform-fleet', label: 'Fleet · Tenants' },
  activeModuleId: 'platform-fleet',
  onModuleSelect: () => {},
};

describe('<PlatformOwnerShell/>', () => {
  it('pinta la navegación de flota y el contenido', () => {
    render(
      <PlatformOwnerShell {...baseProps}>
        <p>flota</p>
      </PlatformOwnerShell>,
    );
    expect(screen.getByRole('heading', { name: 'Fleet · Tenants' })).toBeInTheDocument();
    expect(screen.getByText('flota')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fleet · Tenants' })).toBeInTheDocument();
  });

  it('no renderiza selector de tenant', () => {
    render(
      <PlatformOwnerShell {...baseProps}>
        <p>x</p>
      </PlatformOwnerShell>,
    );
    expect(screen.queryByRole('button', { name: /Cambiar de tenant|Tenant único/ })).toBeNull();
  });
});
