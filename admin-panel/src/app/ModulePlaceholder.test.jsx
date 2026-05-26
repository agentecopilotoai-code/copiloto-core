import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ModulePlaceholder } from './ModulePlaceholder.jsx';

describe('<ModulePlaceholder/>', () => {
  const module = {
    label: 'Mi módulo',
    summary: 'Descripción del módulo',
    scope: ['Alcance 1', 'Alcance 2'],
  };
  const tenant = { label: 'Tenant Demo' };

  it('pinta el label, summary y scope del módulo', () => {
    render(<ModulePlaceholder module={module} tenant={tenant} />);
    expect(screen.getByRole('heading', { name: 'Mi módulo' })).toBeInTheDocument();
    expect(screen.getByText('Descripción del módulo')).toBeInTheDocument();
    expect(screen.getByText('Alcance 1')).toBeInTheDocument();
    expect(screen.getByText('Alcance 2')).toBeInTheDocument();
  });

  it('muestra el label del tenant activo', () => {
    render(<ModulePlaceholder module={module} tenant={tenant} />);
    expect(screen.getByText('Tenant Demo')).toBeInTheDocument();
  });

  it('tolera tenant ausente sin reventar', () => {
    render(<ModulePlaceholder module={module} />);
    expect(screen.getByRole('heading', { name: 'Mi módulo' })).toBeInTheDocument();
  });
});
