import { useCallback, useEffect, useState } from 'react';

import styles from './ThemeToggle.module.css';

/**
 * UI-012 — Toggle de tema tri-estado (auto / light / dark) con persistencia
 * local. Se monta en el topbar de los 3 shells (Tenant, PlatformOwner, ReadOnly).
 *
 * Contrato:
 *   - estado por defecto `auto`: no se setea `data-theme` en `<html>`, así el
 *     `@media (prefers-color-scheme: dark)` decide por el SO;
 *   - `light` / `dark`: se escribe `<html data-theme="light|dark">`, anulando
 *     el media query del SO;
 *   - persistencia: `localStorage[copilotoia:theme]` ∈ `{auto, light, dark}`;
 *   - en mount, lee localStorage y aplica el `data-theme` (o lo borra si
 *     `auto`/inválido);
 *   - acceso a `localStorage` y `document` con guards (SSR-safe / jsdom-safe).
 */
export const THEME_STORAGE_KEY = 'copilotoia:theme';
const THEME_ORDER = ['auto', 'light', 'dark'];
const THEME_LABELS = {
  auto: { label: 'Auto', glyph: 'A', aria: 'Tema: auto — clic para cambiar a claro' },
  light: { label: 'Claro', glyph: '☼', aria: 'Tema: claro — clic para cambiar a oscuro' },
  dark: { label: 'Oscuro', glyph: '☾', aria: 'Tema: oscuro — clic para volver a auto' },
};

function readStoredTheme() {
  if (typeof window === 'undefined') return 'auto';
  try {
    const raw = window.localStorage?.getItem(THEME_STORAGE_KEY);
    return THEME_ORDER.includes(raw) ? raw : 'auto';
  } catch {
    return 'auto';
  }
}

function applyTheme(theme) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (!root) return;
  if (theme === 'auto') {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = theme;
  }
}

function persistTheme(theme) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage?.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* localStorage puede estar deshabilitado (modo privado, etc). El toggle
       sigue funcionando in-memory para esta sesión. */
  }
}

function nextTheme(current) {
  const idx = THEME_ORDER.indexOf(current);
  return THEME_ORDER[(idx + 1) % THEME_ORDER.length];
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const handleClick = useCallback(() => {
    setTheme((prev) => {
      const next = nextTheme(prev);
      persistTheme(next);
      return next;
    });
  }, []);

  const meta = THEME_LABELS[theme] ?? THEME_LABELS.auto;

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={handleClick}
      aria-label={meta.aria}
      title={meta.aria}
      data-theme-state={theme}
    >
      <span className={styles.glyph} aria-hidden="true">
        {meta.glyph}
      </span>
      <span className={styles.label}>{meta.label}</span>
    </button>
  );
}
