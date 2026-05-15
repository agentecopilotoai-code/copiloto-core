import { useCallback, useEffect, useState } from 'react';

import { PageHeader } from '../../components/ui/index.js';
import { THEME_STORAGE_KEY } from '../../app/shells/components/ThemeToggle.jsx';
import styles from './Account.module.css';
import { THEME_OPTIONS } from './accountData.js';

function readStoredTheme() {
  if (typeof window === 'undefined') return 'auto';
  try {
    const raw = window.localStorage?.getItem(THEME_STORAGE_KEY);
    return ['auto', 'light', 'dark'].includes(raw) ? raw : 'auto';
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
    /* localStorage puede estar deshabilitado; el cambio in-memory se mantiene. */
  }
}

/**
 * UI-016.7 — `/account/preferences`.
 *
 * Override del tema por usuario. Comparte estado con el `<ThemeToggle/>` del
 * topbar (UI-012): ambos leen/escriben la misma clave `copilotoia:theme` y
 * aplican `<html data-theme="...">`. Esta página solo cambia la UI de elección
 * (radio cards vs. el toggle tri-estado del topbar).
 *
 * Sin persistencia server-side hasta UI-016.7-FU.
 */
export function AccountPreferences() {
  const [theme, setTheme] = useState(() => readStoredTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const onSelect = useCallback((next) => {
    setTheme(next);
    persistTheme(next);
  }, []);

  return (
    <section className={styles.section}>
      <PageHeader
        eyebrow="Cuenta · apariencia"
        title="Apariencia"
        description="El sistema usa el tema del sistema operativo por defecto. Puedes forzarlo aquí solo para esta sesión."
      />

      <fieldset className={styles.themeCards} aria-label="Tema de la interfaz">
        {THEME_OPTIONS.map((option) => {
          const isActive = theme === option.value;
          const cardClass = isActive
            ? `${styles.themeCard} ${styles.themeCardActive}`
            : styles.themeCard;
          return (
            <label key={option.value} className={cardClass} data-theme-card={option.value}>
              <input
                type="radio"
                name="account-theme"
                value={option.value}
                checked={isActive}
                onChange={() => onSelect(option.value)}
                className={styles.themeCardInput}
                aria-describedby={`theme-desc-${option.value}`}
              />
              <span className={styles.themeCardLabel}>{option.label}</span>
              <p
                id={`theme-desc-${option.value}`}
                className={styles.themeCardDescription}
              >
                {option.description}
              </p>
            </label>
          );
        })}
      </fieldset>
    </section>
  );
}
