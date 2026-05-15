import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { adminPath } from '../../../services/adminSession.js';
import styles from './ShellSidebar.module.css';

const COLLAPSE_STORAGE_KEY = 'copilotoia:sidebar-collapsed';
const COLLAPSE_DOC_ATTR = 'data-sidebar-collapsed';

function userInitials(profile) {
  const source = profile?.name || profile?.email || profile?.sub || 'U';
  const parts = source.trim().split(/\s+/);
  const initials = parts.length > 1 ? parts[0][0] + parts[1][0] : source.slice(0, 2);
  return initials.toUpperCase();
}

/**
 * UI-019 — Hook que sincroniza el estado `collapsed` con:
 *   - `localStorage["copilotoia:sidebar-collapsed"]` (persistencia entre sesiones)
 *   - `<html data-sidebar-collapsed="true">` (el `shell.module.css` reacciona
 *     desde ahí para reducir la columna del grid sin necesidad de cablear
 *     props por todos los `*Shell.jsx`).
 */
function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false;
    try {
      return window.localStorage.getItem(COLLAPSE_STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(COLLAPSE_STORAGE_KEY, collapsed ? '1' : '0');
    } catch {
      /* localStorage podría no estar disponible (Safari private mode); el
         estado en memoria sigue siendo válido para la sesión. */
    }
    if (typeof document !== 'undefined' && document.documentElement) {
      if (collapsed) {
        document.documentElement.setAttribute(COLLAPSE_DOC_ATTR, 'true');
      } else {
        document.documentElement.removeAttribute(COLLAPSE_DOC_ATTR);
      }
    }
  }, [collapsed]);

  return [collapsed, setCollapsed];
}

/**
 * Tarjeta de usuario del sidebar. El avatar + nombre son un `<Link>` a
 * `/account/profile` (UI-016.7) — el HTML T3 deja claro que "estas pantallas
 * viven detrás del avatar del sidebar". El botón "Salir" sigue siendo el
 * submit del form POST a `/admin/logout` que Auth0 espera.
 *
 * En estado colapsado, los meta + form de logout se ocultan (CSS) y solo
 * queda el avatar como link a la cuenta.
 */
function UserCard({ profile, collapsed }) {
  const displayName = profile?.name || profile?.email || profile?.sub || 'Usuario';
  const role = profile?.roles?.length ? profile.roles[0] : 'sin rol';
  return (
    <div className={styles.sidebarFooter}>
      <Link
        to="/account/profile"
        className={styles.userTrigger}
        aria-label={`Abrir mi cuenta (${displayName})`}
        title={collapsed ? `Abrir mi cuenta (${displayName})` : undefined}
      >
        <span className={styles.userAvatar} aria-hidden="true">
          {profile?.picture ? <img alt="" src={profile.picture} /> : userInitials(profile)}
        </span>
        <span className={styles.userMeta}>
          <strong>{displayName}</strong>
          <small>{role}</small>
        </span>
      </Link>
      <form className={styles.logoutForm} method="post" action={adminPath('/admin/logout')}>
        <button className={styles.logoutButton} type="submit">
          Salir
        </button>
      </form>
    </div>
  );
}

/**
 * UI-019 — Sidebar compartido por los 3 shells (Tenant / Viewer / Platform):
 *   - Header (brand + tenant switcher + toggle) y footer (avatar + logout)
 *     quedan anclados; solo `<nav>` scrollea.
 *   - Cada sección lleva un icono SVG inline (mismo patrón que `ShellBottomNav`).
 *   - Estado `collapsed` persistido en localStorage; reduce el rail a 64px
 *     mostrando solo iconos cuando está activo.
 *
 * @param {{
 *   navGroups: Array<{section: string, items: Array<{id, label, disabled}>}>,
 *   activeModuleId?: string,
 *   onModuleSelect: (moduleId: string) => void,
 *   profile?: object,
 *   tenantSwitcher?: import('react').ReactNode,
 *   badge?: import('react').ReactNode,
 * }} props
 */
export function ShellSidebar({
  navGroups,
  activeModuleId,
  onModuleSelect,
  profile,
  tenantSwitcher = null,
  badge = null,
}) {
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const toggle = useCallback(() => setCollapsed((c) => !c), [setCollapsed]);

  return (
    <aside
      className={styles.sidebar}
      data-collapsed={collapsed ? 'true' : 'false'}
      data-testid="shell-sidebar"
    >
      <div className={styles.sidebarHeader}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            IA
          </span>
          <div className={styles.brandText}>
            <strong>CopilotoIA</strong>
            <small>Admin Panel</small>
          </div>
          <button
            type="button"
            className={styles.collapseToggle}
            onClick={toggle}
            aria-label={collapsed ? 'Expandir barra lateral' : 'Colapsar barra lateral'}
            aria-pressed={collapsed}
            title={collapsed ? 'Expandir barra lateral' : 'Colapsar barra lateral'}
          >
            <span aria-hidden="true">{collapsed ? svgChevronRight() : svgChevronLeft()}</span>
          </button>
        </div>

        {tenantSwitcher ? <div className={styles.extraSlot}>{tenantSwitcher}</div> : null}
        {badge ? <div className={styles.extraSlot}>{badge}</div> : null}
      </div>

      <nav
        className={`${styles.sidebarBody} ${styles.nav}`}
        aria-label="Módulos de administración"
      >
        {navGroups.map((group) => (
          <div key={group.section} className={styles.navGroup}>
            <p className={styles.navSectionHeader}>
              <span className={styles.navSectionIcon} aria-hidden="true">
                {iconForSection(group.section)}
              </span>
              <span className={styles.navSectionLabel}>{group.section}</span>
            </p>
            {group.items.map((item) => {
              if (item.disabled) {
                return (
                  <span
                    key={item.id}
                    className={`${styles.navItem} ${styles.navItemDisabled}`}
                    aria-disabled="true"
                    title={collapsed ? item.label : undefined}
                  >
                    <span className={styles.navItemIcon} aria-hidden="true">
                      {iconForSection(group.section)}
                    </span>
                    <span className={styles.navItemLabel}>{item.label}</span>
                  </span>
                );
              }
              return (
                <button
                  key={item.id}
                  type="button"
                  className={
                    item.id === activeModuleId
                      ? `${styles.navItem} ${styles.navItemActive}`
                      : styles.navItem
                  }
                  aria-current={item.id === activeModuleId ? 'page' : undefined}
                  aria-label={collapsed ? item.label : undefined}
                  title={collapsed ? item.label : undefined}
                  onClick={() => onModuleSelect(item.id)}
                >
                  <span className={styles.navItemIcon} aria-hidden="true">
                    {iconForSection(group.section)}
                  </span>
                  <span className={styles.navItemLabel}>{item.label}</span>
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <UserCard profile={profile} collapsed={collapsed} />
    </aside>
  );
}

/**
 * Mapa de iconos por nombre de sección (`nav.js`). Sigue el patrón inline-SVG
 * de `ShellBottomNav` (UI-016.8): `stroke="currentColor"` para heredar el
 * color del contenedor + `aria-hidden="true"` para que solo el label sea
 * leído por screen readers.
 *
 * Si una sección no tiene icono propio, cae al fallback genérico (`svgDots`).
 */
function iconForSection(section) {
  switch (section) {
    case 'Inicio':
      return svgHome();
    case 'Conversaciones':
      return svgChat();
    case 'Hoy':
      return svgCalendar();
    case 'Negocio':
      return svgBriefcase();
    case 'IA & Canales':
      return svgSparkles();
    case 'Operación':
      return svgListCheck();
    case 'Configuración':
      return svgCog();
    case 'Lectura':
      return svgEye();
    case 'Plataforma':
      return svgLayers();
    case 'Observability':
      return svgChart();
    case 'Operaciones':
      return svgListCheck();
    case 'Audit global':
      return svgShield();
    case 'Acceso':
      return svgKey();
    default:
      return svgDots();
  }
}

const SVG_PROPS = {
  viewBox: '0 0 24 24',
  width: '18',
  height: '18',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: '2',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

function svgHome() {
  return (
    <svg {...SVG_PROPS} data-icon="home">
      <path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />
    </svg>
  );
}

function svgChat() {
  return (
    <svg {...SVG_PROPS} data-icon="chat">
      <path d="M21 12a8 8 0 0 1-11.5 7.2L4 21l1.8-5.5A8 8 0 1 1 21 12z" />
    </svg>
  );
}

function svgCalendar() {
  return (
    <svg {...SVG_PROPS} data-icon="calendar">
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 11h18" />
    </svg>
  );
}

function svgBriefcase() {
  return (
    <svg {...SVG_PROPS} data-icon="briefcase">
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18" />
    </svg>
  );
}

function svgSparkles() {
  return (
    <svg {...SVG_PROPS} data-icon="sparkles">
      <path d="M12 3v4M12 17v4M5 12H3M21 12h-2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M6.3 17.7l1.4-1.4M16.3 7.7l1.4-1.4" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function svgListCheck() {
  return (
    <svg {...SVG_PROPS} data-icon="list-check">
      <path d="M9 6h12M9 12h12M9 18h12M3 6l1.5 1.5L7 5M3 12l1.5 1.5L7 11M3 18l1.5 1.5L7 17" />
    </svg>
  );
}

function svgCog() {
  return (
    <svg {...SVG_PROPS} data-icon="cog">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  );
}

function svgEye() {
  return (
    <svg {...SVG_PROPS} data-icon="eye">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function svgLayers() {
  return (
    <svg {...SVG_PROPS} data-icon="layers">
      <path d="M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
    </svg>
  );
}

function svgChart() {
  return (
    <svg {...SVG_PROPS} data-icon="chart">
      <path d="M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-7" />
    </svg>
  );
}

function svgShield() {
  return (
    <svg {...SVG_PROPS} data-icon="shield">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function svgKey() {
  return (
    <svg {...SVG_PROPS} data-icon="key">
      <circle cx="7" cy="15" r="4" />
      <path d="M10 12l11-11M16 7l3 3M14 9l3 3" />
    </svg>
  );
}

function svgDots() {
  return (
    <svg {...SVG_PROPS} data-icon="dots">
      <circle cx="6" cy="12" r="1.4" />
      <circle cx="12" cy="12" r="1.4" />
      <circle cx="18" cy="12" r="1.4" />
    </svg>
  );
}

function svgChevronLeft() {
  return (
    <svg {...SVG_PROPS} width="16" height="16" data-icon="chevron-left">
      <path d="M15 6l-6 6 6 6" />
    </svg>
  );
}

function svgChevronRight() {
  return (
    <svg {...SVG_PROPS} width="16" height="16" data-icon="chevron-right">
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}
