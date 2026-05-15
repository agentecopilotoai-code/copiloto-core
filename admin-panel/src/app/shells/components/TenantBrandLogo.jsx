import styles from './TenantBrandLogo.module.css';

/**
 * UI-012 — Slot de logo personalizado del tenant. Si el backend expone
 * `tenant.brand_logo_url` (campo todavía NO persistido a 2026-05-15; ver
 * follow-up flagged en `docs/DONE.md`), renderiza un `<img>`; en su defecto
 * cae a las iniciales del tenant (mismo helper que `TenantSwitcher`).
 *
 * El componente es **defensivo**: acepta `tenant = null/undefined` y siempre
 * devuelve algo renderizable (fallback genérico `"C"` de CopilotoIA).
 *
 * @param {{ tenant?: { brand_logo_url?: string, display_name?: string, slug?: string, name?: string } }} props
 */
function tenantLabel(tenant) {
  return tenant?.display_name || tenant?.name || tenant?.slug || 'CopilotoIA';
}

function tenantInitials(tenant) {
  const source = tenant?.display_name || tenant?.name || tenant?.slug || 'CO';
  const cleaned = source.replace(/[^a-zA-Z0-9]/g, '');
  return cleaned.slice(0, 2).toUpperCase() || 'CO';
}

export function TenantBrandLogo({ tenant }) {
  const logoUrl = tenant?.brand_logo_url;
  const label = tenantLabel(tenant);

  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={`Logo de ${label}`}
        className={styles.logo}
      />
    );
  }

  return (
    <span
      className={styles.fallback}
      role="img"
      aria-label={`Logo de ${label}`}
    >
      {tenantInitials(tenant)}
    </span>
  );
}
