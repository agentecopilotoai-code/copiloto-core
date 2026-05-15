import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AccountPreferences } from './AccountPreferences.jsx';
import { THEME_STORAGE_KEY } from '../../app/shells/components/ThemeToggle.jsx';

describe('<AccountPreferences/>', () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    window.localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it('pinta los 3 radio cards: Auto, Claro, Oscuro', () => {
    render(<AccountPreferences />);
    expect(screen.getByRole('radio', { name: /Auto/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Claro/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Oscuro/ })).toBeInTheDocument();
  });

  it('por defecto selecciona "Auto" cuando localStorage está vacío', () => {
    render(<AccountPreferences />);
    expect(screen.getByRole('radio', { name: /Auto/ })).toBeChecked();
  });

  it('lee la preferencia previa del localStorage compartido con UI-012', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    render(<AccountPreferences />);
    expect(screen.getByRole('radio', { name: /Oscuro/ })).toBeChecked();
  });

  it('al elegir "Oscuro" persiste en localStorage y aplica data-theme', async () => {
    render(<AccountPreferences />);
    await userEvent.click(screen.getByRole('radio', { name: /Oscuro/ }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('al volver a "Auto" se elimina data-theme del root', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    render(<AccountPreferences />);
    await userEvent.click(screen.getByRole('radio', { name: /Auto/ }));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('auto');
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });
});
