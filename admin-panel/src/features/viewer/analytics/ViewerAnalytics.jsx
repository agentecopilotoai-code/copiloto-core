import { AnalyticsPanel } from '../../../components/modules/analytics/AnalyticsPanel.jsx';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';

/**
 * UI-010.2 — Viewer · Lectura · Analítica.
 *
 * Versión read-only de la analítica del tenant. Es un **wrapper fino** sobre el
 * `AnalyticsPanel` ya existente (`src/components/modules/analytics/`) — el panel
 * legacy se reusa **verbatim** porque ya es read-only por naturaleza (no expone
 * ningún CTA de export, edit ni descarga; sus únicos controles son selectores
 * de rango/tab/refresh). Reutilizarlo intacto evita duplicar lógica de fetch y
 * deja al legacy en su path actual, donde 5 tests estáticos del backend
 * (`test_analytics_static.py`, `test_analytics_agents_static.py`,
 * `test_funnel_attribution_static.py`, `test_referrer_tracking_static.py`,
 * `test_web_widget_static.py`) lo referencian.
 *
 * El gating de permisos lo hace este orquestador con
 * `<RequirePermission capability="analytics.tenant.read" mode="R">` — la
 * capability ya existía en `permissions/matrix.js` (viewer = R). El
 * `ReadOnlyShell` (UI-002) añade el banner permanente «Modo solo lectura»
 * alrededor del contenido. Criterio global UI-010 («100% de las acciones write
 * ocultas») se satisface por construcción: `AnalyticsPanel` no renderiza
 * ninguna acción write.
 *
 * Referencia visual: `docs/HTML DESIGN/Viewer/34 _ Lectura _ Analítica.html`.
 * Diferencia intencional declarada: el HTML del mockup muestra botones de
 * «Exportar PDF» y similares; ese chrome no existe en `AnalyticsPanel` y no se
 * va a inventar (no hay endpoint que lo soporte y el criterio global UI-010
 * exige ocultar cualquier write action).
 *
 * @param {{ module?: object, session: object, tenant: object }} props
 */
export function ViewerAnalytics({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });

  return (
    <RequirePermission permissions={permissions} capability="analytics.tenant.read" mode="R">
      <AnalyticsPanel module={module} session={session} tenant={tenant} />
    </RequirePermission>
  );
}
