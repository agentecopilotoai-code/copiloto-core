import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

import { AccountShell } from './AccountShell.jsx';

function renderAt(path) {
  const router = createMemoryRouter(
    [
      {
        path: '/account',
        element: <AccountShell />,
        children: [
          { path: 'profile', element: <p>perfil</p> },
          { path: 'preferences', element: <p>apariencia</p> },
          { path: 'notifications', element: <p>notificaciones</p> },
          { path: 'sessions', element: <p>sesiones</p> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

describe('<AccountShell/>', () => {
  it('pinta brand, back button y nav lateral de 4 secciones', () => {
    renderAt('/account/profile');
    expect(screen.getByText('CopilotoIA')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Volver al panel/ })).toBeInTheDocument();
    for (const label of ['Perfil', 'Apariencia', 'Notificaciones', 'Sesiones']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
  });

  it('marca la sub-ruta activa con aria-current=page', () => {
    renderAt('/account/preferences');
    expect(screen.getByRole('link', { name: 'Apariencia' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'Perfil' })).not.toHaveAttribute('aria-current');
  });

  it('renderiza el contenido del child Outlet de la ruta activa', () => {
    renderAt('/account/notifications');
    expect(screen.getByText('notificaciones')).toBeInTheDocument();
  });

  it('expone form POST a /admin/logout', () => {
    renderAt('/account/profile');
    const logoutBtn = screen.getByRole('button', { name: 'Cerrar sesión' });
    const form = logoutBtn.closest('form');
    expect(form).toHaveAttribute('method', 'post');
    expect(form?.getAttribute('action')).toMatch(/\/admin\/logout$/);
  });
});
