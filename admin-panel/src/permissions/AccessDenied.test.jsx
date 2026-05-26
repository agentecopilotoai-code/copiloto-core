import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AccessDenied } from './AccessDenied.jsx';

describe('<AccessDenied/> (UI-016.6 refactor)', () => {
  it('muestra el heading del HTML T2 + capability + modo', () => {
    render(<AccessDenied capability="services.write" mode="RW" />);
    expect(
      screen.getByRole('heading', { level: 1, name: 'No tienes acceso a este módulo' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/services\.write/)).toBeInTheDocument();
    expect(screen.getByText(/edición/i)).toBeInTheDocument();
  });

  it('en modo R describe acceso de lectura', () => {
    render(<AccessDenied capability="campaigns.write" mode="R" />);
    // Lectura para campaigns.write — el usuario ni siquiera puede ver el módulo.
    expect(screen.getByText(/lectura/i)).toBeInTheDocument();
    expect(screen.getByText(/campaigns\.write/)).toBeInTheDocument();
  });

  it('mantiene "Acceso restringido" como microcopy legacy (regex de tests por módulo)', () => {
    render(<AccessDenied capability="services.write" mode="R" />);
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
  });

  it('dispara onGoHome al click en "Volver al inicio"', async () => {
    const onGoHome = vi.fn();
    render(<AccessDenied capability="services.write" mode="R" onGoHome={onGoHome} />);
    await userEvent.click(screen.getByRole('button', { name: 'Volver al inicio' }));
    expect(onGoHome).toHaveBeenCalledTimes(1);
  });

  it('renderiza children debajo del body cuando se pasan', () => {
    render(
      <AccessDenied capability="x.read" mode="R">
        <span>Slot adicional</span>
      </AccessDenied>,
    );
    expect(screen.getByText('Slot adicional')).toBeInTheDocument();
  });

  // BUG-002: garantiza escape hatch desde CUALQUIER AccessDenied. Sin esto,
  // un usuario sin permisos para volver al home (rol vacío, capabilities
  // nuevas, tenant sin acceso) queda lockeado en loop sin poder cerrar sesión.
  it('siempre incluye un form de logout como secondary action', () => {
    const { container } = render(<AccessDenied capability="x.read" mode="R" />);
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument();
    const form = container.querySelector('form[method="post"]');
    expect(form).not.toBeNull();
    expect(form.getAttribute('action')).toMatch(/\/admin\/logout$/);
  });

  it('sin onGoHome usa window.location.assign("/admin/")', async () => {
    const original = window.location;
    let assigned = null;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { assign: (url) => { assigned = url; } },
    });
    try {
      render(<AccessDenied capability="x.read" mode="R" />);
      await userEvent.click(screen.getByRole('button', { name: 'Volver al inicio' }));
      expect(assigned).toBe('/admin/');
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: original,
      });
    }
  });
});
