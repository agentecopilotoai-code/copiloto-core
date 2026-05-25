import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { GdSidebar, _NAV_FOR_TEST } from './GdSidebar.jsx';

const TS = 'tenant-demo';

describe('GdSidebar', () => {
  it('rol radicador ve "Ventanilla Única" pero no "Eventos" (auditor only)', () => {
    render(<GdSidebar roles={['gd.radicador']} tenantSlug={TS} />);
    expect(screen.getByText('Ventanilla Única')).toBeInTheDocument();
    expect(screen.queryByText('Eventos')).toBeNull();
  });

  it('rol auditor ve grupo AUDITORÍA con "Eventos"', () => {
    render(<GdSidebar roles={['gd.auditor']} tenantSlug={TS} />);
    expect(screen.getByText('AUDITORÍA')).toBeInTheDocument();
    expect(screen.getByText('Eventos')).toBeInTheDocument();
  });

  it('rol admin_sistema ve grupo ADMIN', () => {
    render(<GdSidebar roles={['gd.admin_sistema']} tenantSlug={TS} />);
    expect(screen.getByText('Usuarios')).toBeInTheDocument();
    expect(screen.getByText('Periféricos')).toBeInTheDocument();
  });

  it('rol sin permisos no muestra ningún grupo', () => {
    render(<GdSidebar roles={[]} tenantSlug={TS} />);
    expect(screen.queryByText('OPERACIÓN')).toBeNull();
    expect(screen.queryByText('AUDITORÍA')).toBeNull();
  });

  it('marca como active el item con href = currentPath', () => {
    render(
      <GdSidebar
        roles={['gd.radicador']}
        tenantSlug={TS}
        currentPath="/gd/t/tenant-demo/ventanilla"
      />,
    );
    const link = screen.getByText('Ventanilla Única').closest('a');
    expect(link.className).toMatch(/active/);
  });

  it('match parcial: currentPath="/gd/t/tenant-demo/ventanilla/cola" activa Ventanilla Única', () => {
    render(
      <GdSidebar
        roles={['gd.radicador']}
        tenantSlug={TS}
        currentPath="/gd/t/tenant-demo/ventanilla/cola"
      />,
    );
    const link = screen.getByText('Ventanilla Única').closest('a');
    expect(link.className).toMatch(/active/);
  });

  it('items de operación generan URL /gd/t/{slug}/...', () => {
    render(<GdSidebar roles={['gd.radicador']} tenantSlug={TS} />);
    const link = screen.getByText('Ventanilla Única').closest('a');
    expect(link.getAttribute('href')).toBe('/gd/t/tenant-demo/ventanilla');
  });

  it('items de admin generan URL /gd/admin/t/{slug}/... (auto-promote)', () => {
    render(<GdSidebar roles={['gd.admin_sistema']} tenantSlug={TS} />);
    const link = screen.getByText('Usuarios').closest('a');
    // El item declara `subPath: '/admin/usuarios'` y `gdHome` lo promueve
    // automáticamente al sub-tree de admin: NUNCA debe quedar como
    // `/gd/t/{slug}/admin/usuarios` (URL inválida en el nuevo esquema).
    expect(link.getAttribute('href')).toBe('/gd/admin/t/tenant-demo/usuarios');
  });

  it('onNavigate intercepta click y recibe URL absoluta + id', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <GdSidebar
        roles={['gd.radicador']}
        tenantSlug={TS}
        onNavigate={onNavigate}
      />,
    );
    await user.click(screen.getByText('Ventanilla Única'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/t/tenant-demo/ventanilla', 'ventanilla');
  });

  it('sin tenantSlug — fallback al subPath (modo test aislado)', () => {
    render(<GdSidebar roles={['gd.radicador']} />);
    const link = screen.getByText('Ventanilla Única').closest('a');
    // Sin slug, el href queda como el subPath crudo. La nav no funciona
    // pero el render no rompe — útil para tests que solo verifican
    // visibilidad por rol.
    expect(link.getAttribute('href')).toBe('/ventanilla');
  });

  it('user prop renderiza badge con iniciales y rol', () => {
    render(
      <GdSidebar
        roles={['gd.radicador']}
        tenantSlug={TS}
        user={{ nombre: 'Pedro González' }}
      />,
    );
    expect(screen.getByText('Pedro González')).toBeInTheDocument();
    expect(screen.getByText('Radicador (ventanilla)')).toBeInTheDocument();
  });

  it('_NAV_FOR_TEST expone la estructura para snapshot interno', () => {
    expect(_NAV_FOR_TEST.length).toBeGreaterThan(0);
    expect(_NAV_FOR_TEST[0]).toHaveProperty('label');
  });
});
