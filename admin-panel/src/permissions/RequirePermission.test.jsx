import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RequirePermission } from './RequirePermission.jsx';
import { usePermissions } from './usePermissions.js';

describe('<RequirePermission/>', () => {
  function PermsHarness({ profile, tenant, capability, mode, hidden, fallback, children }) {
    const permissions = usePermissions({ profile, tenant });
    return (
      <RequirePermission
        permissions={permissions}
        capability={capability}
        mode={mode}
        hidden={hidden}
        fallback={fallback}
      >
        {children}
      </RequirePermission>
    );
  }

  it('renderiza children cuando hay permiso', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['admin'] }}
        capability="services.write"
        mode="RW"
      >
        <span>Editor de servicios</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Editor de servicios')).toBeInTheDocument();
  });

  it('pinta AccessDenied por defecto cuando no hay permiso', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['viewer'] }}
        capability="services.write"
        mode="RW"
      >
        <span>Editor de servicios</span>
      </PermsHarness>,
    );
    expect(screen.queryByText('Editor de servicios')).not.toBeInTheDocument();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.getByText(/services\.write/)).toBeInTheDocument();
  });

  it('hidden=true devuelve null sin fallback', () => {
    const { container } = render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['viewer'] }}
        capability="services.write"
        mode="RW"
        hidden
      >
        <button type="button">Editar</button>
      </PermsHarness>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('fallback custom se respeta', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['viewer'] }}
        capability="services.write"
        mode="RW"
        fallback={<span>Pide permiso a tu admin</span>}
      >
        <span>Editor</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Pide permiso a tu admin')).toBeInTheDocument();
  });

  it('mode=R permite acceso parcial (contacts.write para agent)', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['agent'] }}
        capability="contacts.write"
        mode="R"
      >
        <span>Edit contact (parcial)</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Edit contact (parcial)')).toBeInTheDocument();
  });

  it('mode=RW bloquea acceso parcial', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['agent'] }}
        capability="contacts.write"
        mode="RW"
        hidden
      >
        <span>Edit contact full</span>
      </PermsHarness>,
    );
    expect(screen.queryByText('Edit contact full')).not.toBeInTheDocument();
  });

});
