import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { ShellSidebar } from './ShellSidebar.jsx';

/**
 * UI-019 — Suite del sidebar refactor.
 *
 * Cobertura:
 *   - Render de secciones + items.
 *   - Icono SVG por sección (presencia del `<svg>` dentro del header de la
 *     sección y dentro de cada item).
 *   - Toggle de colapso: estado inicial expandido, click → `data-collapsed`
 *     pasa a `true`, segundo click vuelve a `false`.
 *   - Persistencia en `localStorage["copilotoia:sidebar-collapsed"]`.
 *   - El `<html>` recibe `data-sidebar-collapsed="true"` cuando se colapsa.
 *   - Items siguen disparando `onModuleSelect` incluso colapsados (click vía
 *     icono).
 *   - `aria-label` del toggle alterna entre "Colapsar..." / "Expandir...".
 *   - Inicialización lee `localStorage` (sidebar empieza colapsado si la key
 *     vale '1').
 */

const SAMPLE_NAV = [
  {
    section: 'Configuración',
    items: [
      { id: 'tenant-setup', label: 'Tenant setup', disabled: false },
      { id: 'team', label: 'Equipo', disabled: false },
    ],
  },
  {
    section: 'Plataforma',
    items: [
      { id: 'platform-fleet', label: 'Flota', disabled: false },
      { id: 'platform-system-health', label: 'Salud del sistema', disabled: false },
    ],
  },
  {
    section: 'Operaciones',
    items: [
      { id: 'platform-incidents', label: 'Incidentes', disabled: false },
      { id: 'platform-fleet-dlq', label: 'Cola saliente', disabled: true },
    ],
  },
];

const baseProps = {
  navGroups: SAMPLE_NAV,
  activeModuleId: 'tenant-setup',
  onModuleSelect: () => {},
  profile: { name: 'Camila Rojas', roles: ['owner'] },
};

function renderSidebar(overrides = {}) {
  return render(
    <MemoryRouter>
      <ShellSidebar {...baseProps} {...overrides} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-sidebar-collapsed');
});

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute('data-sidebar-collapsed');
});

describe('<ShellSidebar/> — UI-019', () => {
  it('renderiza todas las secciones del nav input', () => {
    renderSidebar();
    expect(screen.getByText('Configuración')).toBeInTheDocument();
    expect(screen.getByText('Plataforma')).toBeInTheDocument();
    expect(screen.getByText('Operaciones')).toBeInTheDocument();
  });

  it('renderiza los items navegables como buttons', () => {
    renderSidebar();
    expect(screen.getByRole('button', { name: 'Tenant setup' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Equipo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Flota' })).toBeInTheDocument();
  });

  it('cada sección lleva un icono SVG envuelto en un span aria-hidden', () => {
    renderSidebar();
    const nav = screen.getByRole('navigation', { name: 'Módulos de administración' });
    const sectionTitles = ['Configuración', 'Plataforma', 'Operaciones'];
    for (const title of sectionTitles) {
      const label = within(nav).getByText(title);
      const header = label.closest('p');
      expect(header).not.toBeNull();
      const svg = header.querySelector('svg');
      expect(svg).not.toBeNull();
      const iconWrapper = svg.parentElement;
      expect(iconWrapper).toHaveAttribute('aria-hidden', 'true');
    }
  });

  it('marca el módulo activo con aria-current="page"', () => {
    renderSidebar({ activeModuleId: 'team' });
    expect(screen.getByRole('button', { name: 'Equipo' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('dispara onModuleSelect al click en un item', async () => {
    const onModuleSelect = vi.fn();
    renderSidebar({ onModuleSelect });
    await userEvent.click(screen.getByRole('button', { name: 'Equipo' }));
    expect(onModuleSelect).toHaveBeenCalledWith('team');
  });

  it('renderiza items deshabilitados como span con aria-disabled', () => {
    renderSidebar();
    const dlq = screen.getByText('Cola saliente').closest('span[aria-disabled="true"]');
    expect(dlq).not.toBeNull();
  });

  it('arranca expandido por defecto (sin localStorage)', () => {
    renderSidebar();
    const sidebar = screen.getByTestId('shell-sidebar');
    expect(sidebar).toHaveAttribute('data-collapsed', 'false');
    expect(document.documentElement.hasAttribute('data-sidebar-collapsed')).toBe(false);
  });

  it('click en el toggle colapsa el sidebar y persiste en localStorage', async () => {
    renderSidebar();
    const toggle = screen.getByRole('button', { name: 'Colapsar barra lateral' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(toggle);

    const sidebar = screen.getByTestId('shell-sidebar');
    expect(sidebar).toHaveAttribute('data-collapsed', 'true');
    expect(window.localStorage.getItem('copilotoia:sidebar-collapsed')).toBe('1');
    expect(document.documentElement.getAttribute('data-sidebar-collapsed')).toBe('true');

    // El toggle ahora tiene aria-label inverso.
    expect(screen.getByRole('button', { name: 'Expandir barra lateral' })).toBeInTheDocument();
  });

  it('segundo click en el toggle expande el sidebar de vuelta', async () => {
    renderSidebar();
    await userEvent.click(screen.getByRole('button', { name: 'Colapsar barra lateral' }));
    await userEvent.click(screen.getByRole('button', { name: 'Expandir barra lateral' }));

    const sidebar = screen.getByTestId('shell-sidebar');
    expect(sidebar).toHaveAttribute('data-collapsed', 'false');
    expect(window.localStorage.getItem('copilotoia:sidebar-collapsed')).toBe('0');
    expect(document.documentElement.hasAttribute('data-sidebar-collapsed')).toBe(false);
  });

  it('arranca colapsado si localStorage tiene la key con valor "1"', () => {
    window.localStorage.setItem('copilotoia:sidebar-collapsed', '1');
    renderSidebar();
    const sidebar = screen.getByTestId('shell-sidebar');
    expect(sidebar).toHaveAttribute('data-collapsed', 'true');
    expect(document.documentElement.getAttribute('data-sidebar-collapsed')).toBe('true');
  });

  it('items siguen disparando onModuleSelect cuando el sidebar está colapsado', async () => {
    const onModuleSelect = vi.fn();
    window.localStorage.setItem('copilotoia:sidebar-collapsed', '1');
    renderSidebar({ onModuleSelect });

    // Colapsado → el botón se identifica por aria-label en lugar del texto
    // visible (el span del label tiene `display: none` vía CSS).
    const team = screen.getByRole('button', { name: 'Equipo' });
    await userEvent.click(team);
    expect(onModuleSelect).toHaveBeenCalledWith('team');
  });

  it('el toggle expone aria-pressed sincronizado con el estado', async () => {
    renderSidebar();
    const toggle = screen.getByRole('button', { name: 'Colapsar barra lateral' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(toggle);
    expect(screen.getByRole('button', { name: 'Expandir barra lateral' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('UI-016.7 — la tarjeta de usuario sigue siendo un link a /account/profile', () => {
    renderSidebar();
    const link = screen.getByRole('link', { name: /Abrir mi cuenta \(Camila Rojas\)/ });
    expect(link).toHaveAttribute('href', '/account/profile');
  });

  it('renderiza tenantSwitcher y badge slots cuando se pasan', () => {
    renderSidebar({
      tenantSwitcher: <div data-testid="tenant-switcher-stub">switcher</div>,
      badge: <div data-testid="badge-stub">badge</div>,
    });
    expect(screen.getByTestId('tenant-switcher-stub')).toBeInTheDocument();
    expect(screen.getByTestId('badge-stub')).toBeInTheDocument();
  });

  it('pinta cada SVG section icon canónico + fallback dots para secciones desconocidas', () => {
    const allSectionsNav = [
      'Inicio', 'Conversaciones', 'Hoy', 'Negocio', 'IA & Canales',
      'Operación', 'Configuración', 'Lectura', 'Plataforma',
      'Observability', 'Operaciones', 'Audit global', 'Acceso',
      'Sección Desconocida',
    ].map((s, i) => ({
      section: s,
      items: [{ id: `i${i}`, label: s, disabled: false }],
    }));
    renderSidebar({ navGroups: allSectionsNav });
    // Cada section debe tener un SVG con data-icon.
    const icons = Array.from(document.querySelectorAll('[data-icon]')).map(
      (el) => el.getAttribute('data-icon'),
    );
    expect(icons).toContain('home');
    expect(icons).toContain('chat');
    expect(icons).toContain('calendar');
    expect(icons).toContain('briefcase');
    expect(icons).toContain('sparkles');
    expect(icons).toContain('list-check');
    expect(icons).toContain('cog');
    expect(icons).toContain('eye');
    expect(icons).toContain('layers');
    expect(icons).toContain('chart');
    expect(icons).toContain('shield');
    expect(icons).toContain('key');
    expect(icons).toContain('dots'); // fallback
  });

  it('userInitials: profile.name multi-palabra → primeras letras', () => {
    renderSidebar({ profile: { name: 'María José Pérez', roles: ['admin'] } });
    expect(screen.getByText('MJ')).toBeInTheDocument();
  });

  it('userInitials: profile sin name usa email', () => {
    renderSidebar({ profile: { email: 'lucas@x.co' } });
    expect(screen.getByText('LU')).toBeInTheDocument();
  });

  it('userInitials: profile vacío cae a "U"', () => {
    renderSidebar({ profile: null });
    expect(screen.getByText('U')).toBeInTheDocument();
  });

  it('UserCard pinta picture en lugar de iniciales cuando viene', () => {
    renderSidebar({
      profile: { name: 'X', email: 'x@y.co', picture: 'https://cdn/x.png' },
    });
    expect(document.querySelector('img[src="https://cdn/x.png"]')).not.toBeNull();
  });

  it('UserCard cae a "sin rol" si profile no tiene roles', () => {
    renderSidebar({ profile: { name: 'X' } });
    expect(screen.getByText('sin rol')).toBeInTheDocument();
  });

  it('tolera localStorage no disponible (private mode)', () => {
    const original = window.localStorage;
    Object.defineProperty(window, 'localStorage', {
      get: () => { throw new Error('blocked'); },
      configurable: true,
    });
    try {
      renderSidebar();
      const sidebar = screen.getByTestId('shell-sidebar');
      expect(sidebar).toHaveAttribute('data-collapsed', 'false');
    } finally {
      Object.defineProperty(window, 'localStorage', {
        value: original,
        configurable: true,
      });
    }
  });
});
