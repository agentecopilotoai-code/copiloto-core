import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { adminModules } from '../modules.js';
import { InfluencerShell } from './InfluencerShell.jsx';

const baseProps = {
  profile: { name: 'Camila Rojas', roles: ['owner'] },
  permissions: { role: 'owner', can: () => true },
  modules: adminModules,
  activeModule: { id: 'influencer-casting', label: 'Casting' },
  activeModuleId: 'influencer-casting',
  onModuleSelect: () => {},
  tenantOptions: [
    { id: 't1', slug: 'acme', display_name: 'Acme', role: 'owner' },
  ],
  activeTenantId: 't1',
  onTenantChange: () => {},
  canSwitchTenants: false,
};

function renderShell(children, props = {}) {
  return render(
    <MemoryRouter>
      <InfluencerShell {...baseProps} {...props}>
        {children}
      </InfluencerShell>
    </MemoryRouter>,
  );
}

describe('<InfluencerShell/>', () => {
  it('pinta el módulo cuando está habilitado (Owner)', () => {
    renderShell(<p>contenido influencer</p>, { moduleEnabled: true });
    // Topbar muestra "Ravit Studio" como eyebrow + label del módulo activo.
    expect(screen.getByText('Ravit Studio')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Casting' })).toBeInTheDocument();
    expect(screen.getByText('contenido influencer')).toBeInTheDocument();
  });

  it('muestra banner "Módulo no habilitado" cuando moduleEnabled=false', () => {
    renderShell(<p>contenido influencer</p>, { moduleEnabled: false });
    // El banner sustituye al contenido del módulo (no se renderiza children).
    expect(screen.getByText(/no habilitado/i)).toBeInTheDocument();
    expect(screen.queryByText('contenido influencer')).toBeNull();
    expect(
      screen.getByText(/contacta a tu platform owner/i),
    ).toBeInTheDocument();
  });

  it('aplica data-module="influencer" al shell para CSS gating', () => {
    const { container } = renderShell(<p>x</p>, { moduleEnabled: true });
    const shell = container.querySelector('[data-module="influencer"]');
    expect(shell).not.toBeNull();
  });

  it('sub-nav del módulo usa INFLUENCER_NAV (Estudio · Producción · Recursos)', () => {
    renderShell(<p>x</p>, { moduleEnabled: true });
    // Las 3 secciones de INFLUENCER_NAV deben estar visibles en la sidebar
    // siempre que el rol owner tenga acceso (lo tiene en baseProps con
    // permissions.can () => true).
    expect(screen.getByText('Estudio')).toBeInTheDocument();
    expect(screen.getByText('Producción')).toBeInTheDocument();
    expect(screen.getByText('Recursos')).toBeInTheDocument();
  });
});
