import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { GdSidebar, _NAV_FOR_TEST } from './GdSidebar.jsx';

describe('GdSidebar', () => {
  it('rol radicador ve "Ventanilla Única" pero no "Eventos" (auditor only)', () => {
    render(<GdSidebar roles={['gd.radicador']} />);
    expect(screen.getByText('Ventanilla Única')).toBeInTheDocument();
    expect(screen.queryByText('Eventos')).toBeNull();
  });

  it('rol auditor ve grupo AUDITORÍA con "Eventos"', () => {
    render(<GdSidebar roles={['gd.auditor']} />);
    expect(screen.getByText('AUDITORÍA')).toBeInTheDocument();
    expect(screen.getByText('Eventos')).toBeInTheDocument();
  });

  it('rol admin_sistema ve grupo ADMIN', () => {
    render(<GdSidebar roles={['gd.admin_sistema']} />);
    expect(screen.getByText('Usuarios')).toBeInTheDocument();
    expect(screen.getByText('Periféricos')).toBeInTheDocument();
  });

  it('rol sin permisos no muestra ningún grupo', () => {
    render(<GdSidebar roles={[]} />);
    expect(screen.queryByText('OPERACIÓN')).toBeNull();
    expect(screen.queryByText('AUDITORÍA')).toBeNull();
  });

  it('marca como active el item con path = currentPath', () => {
    render(
      <GdSidebar
        roles={['gd.radicador']}
        currentPath="/gd/ventanilla"
      />,
    );
    const link = screen.getByText('Ventanilla Única').closest('a');
    expect(link.className).toMatch(/active/);
  });

  it('match parcial: currentPath="/gd/ventanilla/cola" activa Ventanilla Única', () => {
    render(
      <GdSidebar
        roles={['gd.radicador']}
        currentPath="/gd/ventanilla/cola"
      />,
    );
    const link = screen.getByText('Ventanilla Única').closest('a');
    expect(link.className).toMatch(/active/);
  });

  it('onNavigate intercepta click y previene navegación nativa', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <GdSidebar
        roles={['gd.radicador']}
        onNavigate={onNavigate}
      />,
    );
    await user.click(screen.getByText('Ventanilla Única'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/ventanilla', 'ventanilla');
  });

  it('user prop renderiza badge con iniciales y rol', () => {
    render(
      <GdSidebar
        roles={['gd.radicador']}
        user={{ nombre: 'Pedro González' }}
      />,
    );
    expect(screen.getByText('Pedro González')).toBeInTheDocument();
    expect(screen.getByText('RADICADOR')).toBeInTheDocument();
  });

  it('_NAV_FOR_TEST expone la estructura para snapshot interno', () => {
    expect(_NAV_FOR_TEST.length).toBeGreaterThan(0);
    expect(_NAV_FOR_TEST[0]).toHaveProperty('label');
  });
});
