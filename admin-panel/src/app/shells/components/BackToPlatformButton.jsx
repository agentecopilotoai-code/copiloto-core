import { useNavigate } from 'react-router-dom';

import styles from '../shell.module.css';

/**
 * BUG-015 — botón "Volver a Platform" para platform_owners que entraron a
 * un tenant (via support_mode "Ver como tenant" o después de crear un
 * tenant nuevo).
 *
 * Antes del fix: el platform_owner quedaba "atrapado" en el tenant shell
 * sin una forma visible de regresar a la vista cross-tenant
 * `/admin/platform/...`. El único workaround era escribir la URL a mano
 * o usar el sidebar del browser (back).
 *
 * Visibilidad: el componente padre (TenantShell) lo monta solo cuando
 * `permissions.isSystemOwner === true` — es decir, cuando el user tiene
 * rol global `owner` o `platform_owner` Y está bajo support_mode (sea
 * permanente via JWT o temporal via cookie BUG-008). Un owner del
 * tenant SIN rol platform no debe ver este botón (no tendría a dónde
 * volver — su home es justamente el tenant).
 *
 * Navegación: va a `/platform` (el index del PlatformShell), que el
 * router redirige al home apropiado del role (`ROLE_HOME.platform_owner
 * = 'platform-fleet'`).
 */
export function BackToPlatformButton() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className={styles.backToPlatformButton}
      onClick={() => navigate('/admin')}
      title="Volver a la vista cross-tenant del platform owner"
    >
      ← Platform
    </button>
  );
}
