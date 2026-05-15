import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { THEME_STORAGE_KEY, ThemeToggle } from './ThemeToggle.jsx';

/**
 * UI-012 — Suite del ThemeToggle.
 *
 * Cobertura:
 *   - Estado inicial = `auto` cuando localStorage está vacío o tiene basura.
 *   - Estado inicial restaurado correctamente desde localStorage en `light`/`dark`.
 *   - Ciclo de clicks `auto → light → dark → auto` aplica/borra
 *     `document.documentElement.dataset.theme` en cada paso.
 *   - Cada cambio escribe el valor nuevo en localStorage.
 *   - `aria-label` describe el estado actual.
 *
 * Notas anti-flaky (lecciones UI-015): los queries usan `findByRole` con
 * timeouts implícitos del testing-library, y el reset de DOM/storage corre en
 * `beforeEach`/`afterEach` para que la suite no acumule efectos entre tests.
 */

describe('<ThemeToggle/>', () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it('arranca en `auto` cuando localStorage está vacío y no setea data-theme', async () => {
    render(<ThemeToggle />);
    const button = await screen.findByRole('button', { name: /Tema: auto/ });
    expect(button.dataset.themeState).toBe('auto');
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it('arranca en `auto` cuando localStorage tiene un valor inválido', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'invalid');
    render(<ThemeToggle />);
    const button = await screen.findByRole('button', { name: /Tema: auto/ });
    expect(button.dataset.themeState).toBe('auto');
  });

  it('arranca en `light` cuando localStorage[copilotoia:theme] === "light" y aplica data-theme', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    render(<ThemeToggle />);
    const button = await screen.findByRole('button', { name: /Tema: claro/ });
    expect(button.dataset.themeState).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('arranca en `dark` cuando localStorage[copilotoia:theme] === "dark" y aplica data-theme', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    render(<ThemeToggle />);
    const button = await screen.findByRole('button', { name: /Tema: oscuro/ });
    expect(button.dataset.themeState).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('cicla auto → light → dark → auto y persiste cada cambio', async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    const button = await screen.findByRole('button', { name: /Tema: auto/ });

    // auto → light
    await user.click(button);
    expect(button.dataset.themeState).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');

    // light → dark
    await user.click(button);
    expect(button.dataset.themeState).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    // dark → auto (data-theme se borra)
    await user.click(button);
    expect(button.dataset.themeState).toBe('auto');
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('auto');
  });

  it('sobrevive a un localStorage.setItem que tira (modo privado / quota)', async () => {
    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    const user = userEvent.setup();
    render(<ThemeToggle />);
    const button = await screen.findByRole('button', { name: /Tema: auto/ });

    // No debe explotar — el componente captura el throw y sigue funcionando in-memory.
    await user.click(button);
    expect(button.dataset.themeState).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    setSpy.mockRestore();
  });
});
