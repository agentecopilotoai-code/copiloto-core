import { useState } from 'react';

import { usePermissions } from '../../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../../app/TenantProvider.jsx';
import { useTenantModules } from '../hooks/useTenantModules.js';
import styles from '../FleetTenants.module.css';

function formatDateTime(value) {
  if (!value) return null;
  try {
    return new Date(value).toLocaleString('es-CO', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return null;
  }
}

/**
 * PLATFORM-MODULES-EXPAND — Panel "Módulos" del FleetDrawer.
 *
 * Renderiza el catálogo de módulos toggleables (`TENANT_MODULES_CATALOG`)
 * con un switch por cada uno. Solo platform_owner ve y opera este panel
 * (gate `RequirePermission capability='platform.tenant_modules.write'`).
 *
 * El owner del tenant no debe poder llegar a este componente — el drawer
 * solo se monta dentro de FleetTenants (capability `platform.tenants.read`).
 * Como defensa en profundidad, este panel envuelve el contenido en otro
 * `RequirePermission` con la capability específica.
 *
 * Acciones críticas:
 *   - Toggle ON → PATCH /platform/tenant-modules/{id}/{code} body.enabled=true
 *   - Toggle OFF → mismo endpoint con body.enabled=false
 *
 * Ambos requieren MFA reciente (validado por el backend). Si el backend
 * responde 403 con "mfa required", el panel muestra el mensaje al usuario;
 * la UI no intenta re-prompt MFA porque ese flujo vive en el shell de
 * autenticación del admin (fuera del alcance de esta feature).
 *
 * @param {{
 *   tenant: {id: string, slug: string, display_name?: string},
 * }} props
 */
/**
 * Wrapper que decide si renderizar el contenido. Hace **early return** sin
 * invocar el hook `useTenantModules` cuando el usuario no es platform_owner —
 * así el owner del tenant ni siquiera dispara el GET a
 * `/platform/tenant-modules` (que de todas formas el backend rechazaría con
 * 403, pero ahorramos round-trip y evitamos un evento de auditoría
 * "consulta denegada").
 */
export function TenantModulesPanel({ tenant }) {
  // BUG-220: usePermissions() auto-resuelve profile/tenant del TenantContext;
  // pasarlos explícito quedó deprecado.
  const permissions = usePermissions();

  const canRead = permissions?.can?.('platform.tenant_modules.read', 'R') ?? false;

  if (!canRead) {
    return null;
  }

  return <TenantModulesContent tenant={tenant} permissions={permissions} />;
}

/**
 * Contenido real del panel. Solo se monta cuando el wrapper confirmó que
 * el usuario tiene `platform.tenant_modules.read`. Aquí vive el hook con
 * fetch + mutación.
 */
function TenantModulesContent({ tenant, permissions }) {
  const { session } = useTenantContext();
  const { rows, loading, error, mutating, toggle } = useTenantModules({ session, tenant });
  const [lastChange, setLastChange] = useState(null);

  const canWrite = permissions?.can?.('platform.tenant_modules.write', 'RW') ?? false;

  async function handleToggle(moduleCode, nextEnabled) {
    setLastChange(null);
    try {
      await toggle(moduleCode, nextEnabled);
      setLastChange({
        code: moduleCode,
        enabled: nextEnabled,
        ts: new Date().toISOString(),
      });
    } catch {
      // El error ya está en `error` del hook — no hacemos nada más.
    }
  }

  return (
    <section className={styles.modulesPanel} aria-label="Módulos del tenant">
      <header className={styles.modulesHeader}>
        <h3 className={styles.modulesTitle}>Módulos contratados</h3>
        <p className={styles.modulesHelp}>
          Activación opt-in por tenant. Cada cambio queda auditado en
          <code> platform.tenant_module.activated|deactivated</code>.
          El owner del tenant no ve este panel — si el módulo está OFF, simplemente
          no aparece en su menú lateral.
        </p>
      </header>

      {loading ? (
        <p className={styles.muted}>Cargando módulos…</p>
      ) : null}

      {error ? (
        <p role="alert" className={styles.modulesError}>
          {error}
        </p>
      ) : null}

      {lastChange ? (
        <p role="status" className={styles.modulesStatus}>
          {lastChange.code} → {lastChange.enabled ? 'activado' : 'desactivado'} ·{' '}
          {formatDateTime(lastChange.ts)}
        </p>
      ) : null}

      <ul className={styles.modulesList}>
        {rows.map((row) => {
          const isMutating = mutating === row.code;
          const activatedLabel = row.activated_at
            ? `Activado ${formatDateTime(row.activated_at)}`
            : 'Nunca activado para este tenant';
          return (
            <li key={row.code} className={styles.moduleRow}>
              <div className={styles.moduleMeta}>
                <span className={styles.moduleLabel}>{row.label}</span>
                <code className={styles.moduleCode}>{row.code}</code>
                <span className={styles.moduleDescription}>{row.description}</span>
                <span className={styles.muted}>{activatedLabel}</span>
              </div>
              {canWrite ? (
                <label className={styles.moduleSwitch}>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={row.enabled}
                    disabled={isMutating}
                    onChange={(event) => handleToggle(row.code, event.target.checked)}
                    aria-label={`${row.enabled ? 'Desactivar' : 'Activar'} ${row.label}`}
                  />
                  <span className={styles.moduleSwitchTrack} aria-hidden="true">
                    <span className={styles.moduleSwitchThumb} />
                  </span>
                  <span className={styles.moduleSwitchValue} aria-hidden="true">
                    {row.enabled ? 'ON' : 'OFF'}
                  </span>
                </label>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
