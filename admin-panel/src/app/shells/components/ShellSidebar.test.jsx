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
    section: 'Inicio',
    items: [{ id: 'dashboard', label: 'Dashboard', disabled: false }],
  },
  {
    section: 'Conversaciones',
    items: [
      { id: 'operations-desk', label: 'Inbox operativo', disabled: false },
      { id: 'contacts', label: 'Contactos', disabled: false },
    ],
  },
  {
    section: 'Negocio',
    items: [
      { id: 'services', label: 'Servicios', disabled: false },
      { id: 'branches', label: 'Sedes', disabled: true },
    ],
  },
  {
    section: 'IA & Canales',
    items: [{ id: 'whatsapp', label: 'WhatsApp', disabled: false }],
  },
  {
    section: 'Operación',
    items: [{ id: 'outbound-dlq', label: 'Cola saliente', disabled: false }],
  },
  {
    section: 'Configuración',
    items: [{ id: 'tenant-setup', label: 'Tenant setup', disabled: false }],
  },
];

const baseProps = {
  navGroups: SAMPLE_NAV,
  activeModuleId: 'dashboard',
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
    expect(screen.getByText('Inicio')).toBeInTheDocument();
    expect(screen.getByText('Conversaciones')).toBeInTheDocument();
    expect(screen.getByText('Negocio')).toBeInTheDocument();
    expect(screen.getByText('IA & Canales')).toBeInTheDocument();
    expect(screen.getByText('Operación')).toBeInTheDocument();
    expect(screen.getByText('Configuración')).toBeInTheDocument();
  });

  it('renderiza los items navegables como buttons', () => {
    renderSidebar();
    expect(screen.getByRole('button', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inbox operativo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'WhatsApp' })).toBeInTheDocument();
  });

  it('cada sección lleva un icono SVG envuelto en un span aria-hidden', () => {
    renderSidebar();
    const nav = screen.getByRole('navigation', { name: 'Módulos de administración' });
    const sectionTitles = ['Inicio', 'Conversaciones', 'Negocio', 'IA & Canales', 'Operación', 'Configuración'];
    for (const title of sectionTitles) {
      const label = within(nav).getByText(title);
      const header = label.closest('p');
      expect(header).not.toBeNull();
      // El header tiene un <svg> renderizado por iconForSection envuelto en
      // un span con aria-hidden="true" para que solo el label sea leído por
      // screen readers (mismo patrón que ShellBottomNav).
      const svg = header.querySelector('svg');
      expect(svg).not.toBeNull();
      const iconWrapper = svg.parentElement;
      expect(iconWrapper).toHaveAttribute('aria-hidden', 'true');
    }
  });

  it('marca el módulo activo con aria-current="page"', () => {
    renderSidebar({ activeModuleId: 'contacts' });
    expect(screen.getByRole('button', { name: 'Contactos' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('dispara onModuleSelect al click en un item', async () => {
    const onModuleSelect = vi.fn();
    renderSidebar({ onModuleSelect });
    await userEvent.click(screen.getByRole('button', { name: 'Servicios' }));
    expect(onModuleSelect).toHaveBeenCalledWith('services');
  });

  it('renderiza items deshabilitados como span con aria-disabled', () => {
    renderSidebar();
    const branches = screen.getByText('Sedes').closest('span[aria-disabled="true"]');
    expect(branches).not.toBeNull();
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
    const services = screen.getByRole('button', { name: 'Servicios' });
    await userEvent.click(services);
    expect(onModuleSelect).toHaveBeenCalledWith('services');
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
});
