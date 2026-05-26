import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RolesAclMatrix } from './RolesAclMatrix.jsx';

describe('<RolesAclMatrix/>', () => {
  it('empty state cuando groups está vacío', () => {
    render(<RolesAclMatrix groups={[]} />);
    expect(screen.getByText('Sin capacidades')).toBeInTheDocument();
  });

  it('empty state cuando groups es null', () => {
    render(<RolesAclMatrix groups={null} />);
    expect(screen.getByText('Sin capacidades')).toBeInTheDocument();
  });

  it('renderiza un Card por grupo con la matriz de capabilities', () => {
    const groups = [
      {
        group: 'Administración del tenant',
        rows: [
          {
            capability: 'team.write',
            access: {
              viewer: null, agent: null, manager: null,
              admin: 'RW', owner: 'RW', platform_owner: null,
            },
          },
          {
            capability: 'team.read',
            access: {
              viewer: null, agent: null, manager: 'R',
              admin: 'R', owner: 'R', platform_owner: null,
            },
          },
        ],
      },
    ];
    render(<RolesAclMatrix groups={groups} />);
    expect(screen.getByText('Administración del tenant')).toBeInTheDocument();
    expect(screen.getByText('2 capacidades')).toBeInTheDocument();
    expect(screen.getByText('team.write')).toBeInTheDocument();
    expect(screen.getByText('team.read')).toBeInTheDocument();
    // Niveles legibles del badge.
    expect(screen.getAllByText('R/W').length).toBeGreaterThan(0);
    expect(screen.getAllByText('R').length).toBeGreaterThan(0);
    // Celdas vacías muestran "—".
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });
});
