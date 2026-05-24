import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { VentanillaHome } from './VentanillaHome.jsx';

describe('VentanillaHome', () => {
  it('radicador ve acciones nuevo entrada/cola', () => {
    render(<VentanillaHome roles={['gd.radicador']} />);
    expect(screen.getByTestId('vu-accion-nuevo-entrada')).toBeInTheDocument();
    expect(screen.getByTestId('vu-accion-cola')).toBeInTheDocument();
  });

  it('sin permisos muestra empty', () => {
    render(<VentanillaHome roles={['gd.usuario_consulta']} />);
    expect(screen.getByText(/No tiene permisos para operar Ventanilla/)).toBeInTheDocument();
  });

  it('click en accion dispara onNavigate', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<VentanillaHome roles={['gd.radicador']} onNavigate={onNavigate} />);
    await user.click(screen.getByTestId('vu-accion-nuevo-entrada'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/ventanilla/nuevo-entrada');
  });

  it('renderiza KPIs si vienen', () => {
    render(
      <VentanillaHome
        roles={['gd.radicador']}
        kpis={{
          radicados_hoy: 18,
          pendientes_clasificacion: 4,
          en_cola: 9,
          anulaciones_mes: 1,
        }}
      />,
    );
    expect(screen.getByTestId('vu-kpis')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
  });

  it('sin KPIs no renderiza esa sección', () => {
    render(<VentanillaHome roles={['gd.radicador']} />);
    expect(screen.queryByTestId('vu-kpis')).toBeNull();
  });
});
