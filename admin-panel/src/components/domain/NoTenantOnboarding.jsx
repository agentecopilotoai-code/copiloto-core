/**
 * Tarjeta de bienvenida para usuarios autenticados que todavía no pertenecen a
 * ningún tenant. Lleva al wizard de creación de tenant, donde quedan como
 * administrador principal.
 *
 * @param {{ onCreateTenant: () => void }} props
 */
export function NoTenantOnboarding({ onCreateTenant }) {
  return (
    <section className="module-card empty-tenant-card">
      <p className="eyebrow">Primer tenant</p>
      <h2>Crea tu tenant para empezar</h2>
      <p className="hint">
        Tu usuario todavía no está asociado a un tenant. Crea uno y quedarás como su
        administrador principal para continuar la configuración.
      </p>
      <button className="primary-action" onClick={onCreateTenant} type="button">
        Crear tenant
      </button>
    </section>
  );
}
