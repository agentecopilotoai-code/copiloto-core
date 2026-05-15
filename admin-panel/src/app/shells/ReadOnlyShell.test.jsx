import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { adminModules } from '../modules.js';
import { ReadOnlyShell } from './ReadOnlyShell.jsx';

const baseProps = {
  profile: { name: 'Patricia Marín', roles: ['viewer'] },
  permissions: {
    role: 'viewer',
    can: (cap) => cap === 'analytics.tenant.read' || cap === 'conversations.view',
  },
  modules: adminModules,
  activeModule: { id: 'analytics', label: 'Analítica' },
  activeModuleId: 'analytics',
  onModuleSelect: () => {},
  tenantOptions: [{ id: 't1', slug: 'acme', display_name: 'Acme', role: 'viewer' }],
  activeTenantId: 't1',
  onTenantChange: () => {},
  canSwitchTenants: false,
};

describe('<ReadOnlyShell/>', () => {
  it('muestra badge y banner de solo lectura', () => {
    render(
      <MemoryRouter>
        <ReadOnlyShell {...baseProps}>
          <p>resumen</p>
        </ReadOnlyShell>
      </MemoryRouter>,
    );
    expect(screen.getByText('Acceso de solo lectura')).toBeInTheDocument();
    expect(screen.getByText('Modo solo lectura')).toBeInTheDocument();
    expect(screen.getByText('resumen')).toBeInTheDocument();
  });

  it('renderiza los módulos sin permiso como deshabilitados (sección "Sin acceso")', () => {
    render(
      <MemoryRouter>
        <ReadOnlyShell {...baseProps}>
          <p>x</p>
        </ReadOnlyShell>
      </MemoryRouter>,
    );
    // contacts.view sí permitido → botón; campaigns sin permiso no está en VIEWER_NAV.
    // UI-010.4: el Viewer ahora ve `viewer-conversations` («Conversaciones»)
    // en vez de `operations-desk` («Operations Desk») — la lista read-only que
    // reusa `InboxList` con `showStartForm={false}`.
    expect(screen.getByRole('button', { name: 'Analítica' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Conversaciones' })).toBeInTheDocument();
    const contactos = screen.getByText('Contactos');
    expect(contactos.tagName).toBe('SPAN');
    expect(contactos).toHaveAttribute('aria-disabled', 'true');
  });
});
