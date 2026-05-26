import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RequirePermission } from './RequirePermission.jsx';
import { computePermissions } from './usePermissions.js';

describe('<RequirePermission/>', () => {
  function PermsHarness({ profile, tenant, capability, mode, hidden, fallback, children }) {
    const permissions = computePermissions({ profile, tenant });
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
        capability="team.write"
        mode="RW"
      >
        <span>Editor de equipo</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Editor de equipo')).toBeInTheDocument();
  });

  it('pinta AccessDenied por defecto cuando no hay permiso', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['viewer'] }}
        capability="team.write"
        mode="RW"
      >
        <span>Editor de equipo</span>
      </PermsHarness>,
    );
    expect(screen.queryByText('Editor de equipo')).not.toBeInTheDocument();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.getByText(/team\.write/)).toBeInTheDocument();
  });

  it('hidden=true devuelve null sin fallback', () => {
    const { container } = render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['viewer'] }}
        capability="team.write"
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
        capability="team.write"
        mode="RW"
        fallback={<span>Pide permiso a tu admin</span>}
      >
        <span>Editor</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Pide permiso a tu admin')).toBeInTheDocument();
  });

  it('mode=R permite lectura de team a manager', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['manager'] }}
        capability="team.read"
        mode="R"
      >
        <span>Lista de equipo</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Lista de equipo')).toBeInTheDocument();
  });

  it('capability=null pasa SIEMPRE (módulos sin capability declarada)', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['viewer'] }}
        capability={null}
        mode="R"
      >
        <span>Sin capability — visible</span>
      </PermsHarness>,
    );
    expect(screen.getByText('Sin capability — visible')).toBeInTheDocument();
  });

  it('mode=RW bloquea acceso a manager (solo lectura)', () => {
    render(
      <PermsHarness
        profile={{}}
        tenant={{ roles: ['manager'] }}
        capability="team.write"
        mode="RW"
        hidden
      >
        <span>Editar equipo</span>
      </PermsHarness>,
    );
    expect(screen.queryByText('Editar equipo')).not.toBeInTheDocument();
  });
});
