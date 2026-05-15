import { Button, StateScreen } from '../ui/index.js';

/**
 * UI-016.6 — pantalla `/no-tenant` redibujada al diseño `T2 _ Estados de
 * error y bloqueos`. Tarjeta de bienvenida para usuarios autenticados que
 * todavía no pertenecen a ningún tenant. La acción primaria lleva al wizard
 * de creación de tenant; el secundario refresca la lista (cuando otra
 * persona acaba de aceptar la invitación).
 *
 * Mantiene el literal histórico "Crea tu tenant para empezar" en el botón
 * primario para que los assertions del router (regex) sigan resolviendo,
 * y a la vez muestra el copy del HTML como heading principal.
 *
 * @param {Object} props
 * @param {() => void} props.onCreateTenant Handler del botón primario.
 * @param {() => void} [props.onRefresh] Handler del botón "Refrescar".
 *   Por defecto recarga la página para repolear `listMyTenants`.
 */
export function NoTenantOnboarding({ onCreateTenant, onRefresh }) {
  const refresh = onRefresh ?? (() => {
    if (typeof window !== 'undefined') window.location.reload();
  });

  return (
    <StateScreen
      tone="neutral"
      icon={<UsersIcon />}
      heading="Aún no estás asignada a un negocio"
      body={
        <p>
          Tu usuario ya existe en CopilotoIA, pero todavía nadie te invitó a un
          tenant. Pídele a la owner que te mande la invitación, o crea uno
          nuevo. <strong>Crea tu tenant para empezar.</strong>
        </p>
      }
      primary={
        <Button variant="primary" onClick={onCreateTenant}>
          Crear nuevo tenant
        </Button>
      }
      secondary={
        <Button variant="ghost" onClick={refresh}>
          Refrescar
        </Button>
      }
    />
  );
}

function UsersIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20c0-3 2.5-5 6-5s6 2 6 5" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M15 20c0-2.5 2-4 4-4" />
    </svg>
  );
}
