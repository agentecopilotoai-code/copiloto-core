import styles from './TenantBrandLogo.module.css';

/**
 * Slot de logo del tenant en el header del shell. En el core puro mostramos
 * iniciales — la carga/personalización del logo es parte de un módulo de
 * branding opcional que se instala sobre el core.
 *
 * @param {{ tenant?: { display_name?: string, slug?: string, name?: string } }} props
 */
function tenantLabel(tenant) {
  return tenant?.display_name || tenant?.name || tenant?.slug || 'Copiloto';
}

function tenantInitials(tenant) {
  const source = tenant?.display_name || tenant?.name || tenant?.slug || 'CO';
  const cleaned = source.replace(/[^a-zA-Z0-9]/g, '');
  return cleaned.slice(0, 2).toUpperCase() || 'CO';
}

export function TenantBrandLogo({ tenant }) {
  return (
    <span
      className={styles.fallback}
      role="img"
      aria-label={`Logo de ${tenantLabel(tenant)}`}
    >
      {tenantInitials(tenant)}
    </span>
  );
}
