import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { GdLanding } from './GdLanding.jsx';

describe('GdLanding', () => {
  it('rol sin acceso muestra empty', () => {
    render(<GdLanding roles={['gd.agente_ia']} />);
    // gd.agente_ia es técnico y NO está en GD_ROLES con permisos UI
    expect(screen.getByText(/No tiene permisos activos/i)).toBeInTheDocument();
  });

  it('radicador ve atajo "Nuevo radicado de entrada"', () => {
    render(<GdLanding roles={['gd.radicador']} />);
    expect(screen.getByText('Nuevo radicado de entrada')).toBeInTheDocument();
  });

  it('CTA "Ir a mi área de trabajo" navega a la landing del rol', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<GdLanding roles={['gd.radicador']} onNavigate={onNavigate} />);
    await user.click(screen.getByText('Ir a mi área de trabajo'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/ventanilla');
  });

  it('click en atajo navega a su path', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<GdLanding roles={['gd.profesional']} onNavigate={onNavigate} />);
    await user.click(screen.getByText('Mis PQRSD pendientes'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/pqrsd/mias');
  });

  it('saluda al usuario si viene', () => {
    render(<GdLanding roles={['gd.radicador']} user={{ nombre: 'Lina' }} />);
    expect(screen.getByText(/Bienvenido, Lina/)).toBeInTheDocument();
  });
});
