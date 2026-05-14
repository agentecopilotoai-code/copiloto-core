import { Card, CardHeader } from '../../../../components/ui/index.js';
import styles from '../Dashboard.module.css';

// Quick links to the modules an Owner/Admin reaches most often from the home.
const QUICK_LINKS = [
  { moduleId: 'operations-desk', label: 'Operations Desk', hint: 'Conversaciones y handoff' },
  { moduleId: 'contacts', label: 'Contactos', hint: 'CRM y fichas de contacto' },
  { moduleId: 'services', label: 'Servicios', hint: 'Catálogo del negocio' },
  { moduleId: 'analytics', label: 'Analítica', hint: 'KPIs, funnel y agentes' },
  { moduleId: 'outbound-dlq', label: 'Outbound DLQ', hint: 'Mensajes fallidos a reintentar' },
  { moduleId: 'campaigns', label: 'Campañas', hint: 'Envíos masivos a segmentos' },
];

/**
 * Quick-link grid for the Owner/Admin dashboard. Each card navigates to a
 * tenant-scoped module via the `onNavigate` callback owned by the view.
 *
 * @param {{ onNavigate: (moduleId: string) => void }} props
 */
export function DashboardQuickLinks({ onNavigate }) {
  return (
    <Card padding="md">
      <CardHeader title="Accesos rápidos" subtitle="Las vistas más usadas del día a día" />
      <ul className={styles.quickGrid}>
        {QUICK_LINKS.map((link) => (
          <li key={link.moduleId}>
            <button
              type="button"
              className={styles.quickCard}
              onClick={() => onNavigate(link.moduleId)}
            >
              <span className={styles.quickLabel}>{link.label}</span>
              <span className={styles.quickHint}>{link.hint}</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
