import { useId, useRef, useState } from 'react';

import styles from './ShellBottomNav.module.css';

/**
 * UI-016.8 — Bottom navigation rail visible solo en viewports móviles
 * (`@media (max-width: 1024px)`, bumped from 480px → 768px → 1024px en
 * BUG-004 tras el feedback codex de que phones modernos en landscape
 * llegan a 932px). En desktop (≥ 1024px) está oculto con `display: none`
 * para que el sidebar normal siga siendo la nav primaria.
 *
 * El HTML T4 dibuja una barra inferior con 5 íconos + labels —
 * "Inicio | Inbox | Citas | Analítica | Más". Cuando el rol tiene más de
 * 4 destinos primarios, el último slot se transforma en "Más" y abre una
 * sheet con los items restantes (resto de la nav agrupada).
 *
 * El componente consume los mismos `navGroups` que `ShellSidebar` (resultado
 * de `resolveNav`) — así la barra inferior queda en sync con la sidebar sin
 * duplicar permisos ni labels.
 *
 * @param {{
 *   navGroups: Array<{section: string, items: Array<{id, label, disabled}>}>,
 *   activeModuleId?: string,
 *   onModuleSelect: (moduleId: string) => void,
 * }} props
 */
export function ShellBottomNav({ navGroups, activeModuleId, onModuleSelect }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const sheetId = useId();
  const sheetTitleId = `${sheetId}-title`;
  const moreButtonRef = useRef(null);

  const flatItems = flattenItems(navGroups);
  if (flatItems.length === 0) return null;

  const showMore = flatItems.length > MAX_PRIMARY_SLOTS;
  const primarySlots = showMore ? flatItems.slice(0, MAX_PRIMARY_SLOTS - 1) : flatItems.slice(0, MAX_PRIMARY_SLOTS);
  const overflow = showMore ? flatItems.slice(MAX_PRIMARY_SLOTS - 1) : [];
  const activeInOverflow = overflow.some((item) => item.id === activeModuleId);

  const closeSheet = () => {
    setMoreOpen(false);
    requestAnimationFrame(() => moreButtonRef.current?.focus());
  };

  return (
    <>
      <nav
        className={styles.bottomNav}
        aria-label="Navegación móvil"
        data-testid="shell-bottom-nav"
      >
        <ul className={styles.list}>
          {primarySlots.map((item) => (
            <li key={item.id} className={styles.slot}>
              <button
                type="button"
                className={
                  item.id === activeModuleId
                    ? `${styles.tab} ${styles.tabActive}`
                    : styles.tab
                }
                aria-current={item.id === activeModuleId ? 'page' : undefined}
                aria-disabled={item.disabled || undefined}
                disabled={item.disabled}
                onClick={() => onModuleSelect(item.id)}
              >
                <span className={styles.icon} aria-hidden="true">
                  {iconFor(item.id)}
                </span>
                <span className={styles.label}>{shortLabel(item.label)}</span>
              </button>
            </li>
          ))}
          {showMore ? (
            <li className={styles.slot}>
              <button
                ref={moreButtonRef}
                type="button"
                className={
                  activeInOverflow
                    ? `${styles.tab} ${styles.tabActive}`
                    : styles.tab
                }
                aria-haspopup="menu"
                aria-expanded={moreOpen}
                aria-controls={sheetId}
                onClick={() => setMoreOpen((open) => !open)}
              >
                <span className={styles.icon} aria-hidden="true">
                  {iconFor('more')}
                </span>
                <span className={styles.label}>Más</span>
              </button>
            </li>
          ) : null}
        </ul>
      </nav>

      {showMore && moreOpen ? (
        <>
          <div
            className={styles.scrim}
            aria-hidden="true"
            onClick={closeSheet}
            data-testid="shell-bottom-nav-scrim"
          />
          <div
            id={sheetId}
            className={styles.sheet}
            role="dialog"
            aria-modal="true"
            aria-labelledby={sheetTitleId}
          >
            <header className={styles.sheetHeader}>
              <h2 id={sheetTitleId} className={styles.sheetTitle}>
                Más módulos
              </h2>
              <button
                type="button"
                className={styles.sheetClose}
                onClick={closeSheet}
                aria-label="Cerrar"
              >
                ×
              </button>
            </header>
            <ul className={styles.sheetList}>
              {overflow.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={
                      item.id === activeModuleId
                        ? `${styles.sheetItem} ${styles.sheetItemActive}`
                        : styles.sheetItem
                    }
                    aria-current={item.id === activeModuleId ? 'page' : undefined}
                    aria-disabled={item.disabled || undefined}
                    disabled={item.disabled}
                    onClick={() => {
                      onModuleSelect(item.id);
                      closeSheet();
                    }}
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : null}
    </>
  );
}

const MAX_PRIMARY_SLOTS = 5;

function flattenItems(navGroups) {
  if (!Array.isArray(navGroups)) return [];
  const out = [];
  for (const group of navGroups) {
    for (const item of group.items ?? []) {
      // El bottom-nav móvil solo expone destinos navegables: omitimos los
      // items deshabilitados (sin permiso) — el sidebar normal ya los pinta
      // en su sección "Sin acceso" cuando aplica.
      if (item.disabled) continue;
      out.push(item);
    }
  }
  return out;
}

/**
 * Recorta labels largos a una palabra corta para que entren en la barra
 * (~64px de ancho por slot a 360px). Conserva la primera palabra del label.
 */
function shortLabel(label) {
  if (!label) return '';
  const first = String(label).trim().split(/\s+|·/)[0];
  return first.length > 10 ? `${first.slice(0, 9)}…` : first;
}

/**
 * Inline SVGs (sin dependencia nueva). Mapeo simple por `id` de módulo;
 * los `id` desconocidos caen al ícono genérico de "más".
 */
function iconFor(id) {
  switch (id) {
    case 'dashboard':
    case 'manager-analytics':
    case 'viewer-summary':
    case 'platform-fleet':
      return svgHome();
    case 'operations-desk':
    case 'my-handoffs':
    case 'viewer-conversations':
      return svgInbox();
    case 'appointments':
    case 'viewer-appointments':
      return svgCalendar();
    case 'analytics':
    case 'viewer-analytics':
    case 'platform-billing':
      return svgChart();
    case 'more':
    default:
      return svgMore();
  }
}

function svgHome() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />
    </svg>
  );
}

function svgInbox() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 13h5l2 3h4l2-3h5" />
      <path d="M5 5h14l2 8v6H3v-6z" />
    </svg>
  );
}

function svgCalendar() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 11h18" />
    </svg>
  );
}

function svgChart() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-7" />
    </svg>
  );
}

function svgMore() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="6" cy="12" r="1.4" />
      <circle cx="12" cy="12" r="1.4" />
      <circle cx="18" cy="12" r="1.4" />
    </svg>
  );
}
