import { useEffect, useState } from 'react';

import { useOptionalTenantContext } from '../../app/TenantProvider.jsx';
import styles from './SupportModeBanner.module.css';

/**
 * BUG-008 — Banner persistente cuando el platform_owner está operando
 * dentro de un tenant ajeno bajo support_mode opt-in temporal.
 *
 * Se renderiza en el `TenantShell` (no en `PlatformOwnerShell` ni en
 * `ReadOnlyShell`). Solo aparece cuando `supportModeOverride.tenantId`
 * matchea el `activeTenantId` actual — esto previene mostrar el banner
 * en tenants donde el platform_owner NO activó el toggle (el cookie es
 * scoped a UN tenant; navegando a otro, el banner se oculta solo).
 *
 * El componente:
 *   - Muestra contador de tiempo restante (HH:MM) que se actualiza cada
 *     30s. Cuando `expiresAt` pasa, el banner igual queda visible pero el
 *     contador dice "Expira pronto"; el backend rechazará las próximas
 *     requests, dando feedback natural al user.
 *   - Botón "Salir de support mode" invoca `deactivateSupportMode`, opcio-
 *     nalmente dispara `onExited` (para que el shell padre navegue al
 *     platform home), y limpia el state — el next render quita el banner.
 *
 * El styling es deliberadamente prominente (color warning + posición
 * sticky al top del workspace) para que el operator NO olvide que está
 * con privilegios elevados en un tenant ajeno.
 *
 * `onExited`: callback opcional que se ejecuta DESPUÉS de
 * `deactivateSupportMode` exitoso. Útil en sub-shells de módulos opt-in
 * para navegar fuera del tenant — sin el callback, el user queda
 * "huérfano" en una página cuyas queries fallan porque ya no tiene cookie
 * de support_mode ni es miembro real del tenant.
 *
 * @param {{ activeTenantId?: string, onExited?: () => void }} props
 */
export function SupportModeBanner({ activeTenantId, onExited }) {
  // Tolera ausencia de contexto — el shell puede renderizarse en tests
  // aislados sin provider. En ese caso, el banner no se monta.
  const ctx = useOptionalTenantContext();
  const supportModeOverride = ctx?.supportModeOverride ?? null;
  const deactivateSupportMode = ctx?.deactivateSupportMode;
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);

  const overrideTenantId = supportModeOverride?.tenantId;
  const expiresAt = supportModeOverride?.expiresAt;
  const isActiveHere =
    Boolean(overrideTenantId)
    && Boolean(activeTenantId)
    && String(overrideTenantId) === String(activeTenantId);

  useEffect(() => {
    if (!isActiveHere) return undefined;
    const interval = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(interval);
  }, [isActiveHere]);

  if (!isActiveHere) return null;

  const expiresAtMs = expiresAt instanceof Date ? expiresAt.getTime() : null;
  const remainingMs = expiresAtMs ? expiresAtMs - now : null;
  const remainingLabel = formatRemaining(remainingMs);

  async function handleExit() {
    if (busy || !deactivateSupportMode) return;
    setBusy(true);
    try {
      await deactivateSupportMode(activeTenantId);
      // Después del exit exitoso, dejá que el shell padre navegue. Sin
      // esto, dentro de un sub-shell el user queda en una página que va
      // a hacer 404 en el próximo fetch (perdió access).
      if (typeof onExited === 'function') {
        onExited();
      }
    } catch (err) {
      // Swallow — el usuario verá que el banner sigue ahí (cookie no
      // se removió server-side) y puede reintentar. Loguear para que
      // quede en la consola del browser si algo se rompe sistemáticamente.
      // eslint-disable-next-line no-console
      console.error('SupportModeBanner: deactivateSupportMode falló', err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.banner} role="status" aria-live="polite">
      <div className={styles.text}>
        <strong>Operando en support_mode.</strong>{' '}
        Acceso temporal cross-tenant como Platform Owner. {remainingLabel}
      </div>
      <button
        type="button"
        className={styles.exitButton}
        onClick={handleExit}
        disabled={busy}
      >
        {busy ? 'Saliendo…' : 'Salir de support mode'}
      </button>
    </div>
  );
}

function formatRemaining(remainingMs) {
  if (remainingMs == null) return '';
  if (remainingMs <= 0) return 'Expira pronto — re-activá si necesitás más tiempo.';
  const minutes = Math.floor(remainingMs / 60_000);
  if (minutes < 1) return 'Expira en menos de 1 min.';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours > 0) return `Expira en ${hours}h ${mins}min.`;
  return `Expira en ${mins} min.`;
}
