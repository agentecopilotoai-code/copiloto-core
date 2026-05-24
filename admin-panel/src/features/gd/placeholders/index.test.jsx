import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import * as placeholders from './index.jsx';

// Solo placeholders aún sin implementación real (los de Ventanilla ya
// fueron reemplazados en bloque UI-2).
const PLACEHOLDER_NAMES = [
  'GdRadicadoFicha',
  'GdBuzonHome', 'GdBuzonDependencia',
  'GdPqrsdPanel', 'GdPqrsdFicha',
  'GdCorrespondenciaInterna', 'GdCorrespondenciaExterna',
  'GdBiblioteca', 'GdPlantillas', 'GdPorFirmar',
  'GdTrdHome', 'GdExpedientes',
  'GdAdminUsuarios', 'GdAdminEstructura', 'GdAdminCatalogos',
  'GdAdminParametros', 'GdAdminPerifericos', 'GdSeguridad',
  'GdAuditoria', 'GdReportes',
  'GdBuscar', 'GdConsulta',
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
