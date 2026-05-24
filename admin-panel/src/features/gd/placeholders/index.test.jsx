import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import * as placeholders from './index.jsx';

// Solo placeholders aún sin implementación real (UI-2 y UI-3 ya
// reemplazaron toda Ventanilla incluyendo ficha + búsqueda).
const PLACEHOLDER_NAMES = [
  'GdAdminPerifericos',
];

describe('placeholders de bloques posteriores', () => {
  it('exporta GdHome (landing rol-aware)', () => {
    expect(placeholders.GdHome).toBeTypeOf('function');
  });

  it('GdHome renderiza GdShell + GdLanding', () => {
    const { container } = render(
      <placeholders.GdHome roles={['gd.radicador']} />,
    );
    expect(container.querySelector('.gd-shell-root')).toBeTruthy();
  });

  it.each(PLACEHOLDER_NAMES)('placeholder %s renderiza shell + título', (name) => {
    const Cmp = placeholders[name];
    expect(Cmp).toBeTypeOf('function');
    render(<Cmp roles={['gd.admin_sistema']} />);
    expect(screen.getByText(/Vista en construcción/)).toBeInTheDocument();
  });
});
