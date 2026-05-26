import { Modal, StatusBadge } from '../../../../components/ui/index.js';
import { TenantModulesPanel } from './TenantModulesPanel.jsx';
import { TenantMembersPanel } from './TenantMembersPanel.jsx';
import styles from '../FleetTenants.module.css';

const STATUS_TONE = {
  active: 'success',
  trial: 'accent',
  suspended: 'warning',
  churned: 'danger',
};

function formatDateTime(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('es-CO', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

/**
 * Tenant detail drawer (modal). Shows the profile pulled from the fleet list
 * plus a "Ver como tenant" CTA the platform owner uses to support-mode into
 * the tenant. Future enhancements (health snapshot, billing card, recent
 * incidents) land with UI-006.2 / UI-006.3 / UI-006.4 — kept out of scope on
 * purpose so this drawer stays under the 400 LOC mandate.
 *
 * @param {{
 *   tenant: object | null,
 *   onClose: () => void,
 *   onSupportInto: (tenant: object) => void,
 * }} props
 */
export function FleetDrawer({ tenant, onClose, onSupportInto, session }) {
  if (!tenant) return null;

  const rows = [
    ['Slug', tenant.slug],
    ['Razón social', tenant.legal_name || '—'],
    ['Vertical', tenant.vertical_code || '—'],
    ['Tipo de negocio', tenant.business_type_label || '—'],
    ['País', tenant.country_code || '—'],
    ['Zona horaria', tenant.timezone || '—'],
    ['Miembros', String(tenant.member_count ?? 0)],
    ['Owners', String(tenant.owner_count ?? 0)],
    ['Owner email', tenant.owner_email || 'Sin owner'],
    ['Creado', formatDateTime(tenant.created_at)],
    ['Última actividad', formatDateTime(tenant.last_activity_at || tenant.updated_at)],
  ];

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={tenant.display_name || tenant.legal_name || tenant.slug}
      description={
        <span className={styles.drawerHeadMeta}>
          <StatusBadge tone={STATUS_TONE[tenant.status] || 'neutral'}>{tenant.status}</StatusBadge>
          <span className={styles.muted}>· ID {tenant.id}</span>
        </span>
      }
      footer={
        <div className={styles.drawerActions}>
          <button type="button" className={styles.linkButton} onClick={onClose}>
            Cerrar
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => onSupportInto(tenant)}
          >
            Ver como tenant
          </button>
        </div>
      }
    >
      <dl className={styles.drawerGrid}>
        {rows.map(([label, value]) => (
          <div key={label} className={styles.drawerRow}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {/* Panel de activación de módulos opt-in registrados en TENANT_MODULES_CATALOG. */}
      <TenantModulesPanel tenant={tenant} />

      {/* Gestión de miembros: agregar usuarios al tenant, asignar roles,
          revocar membresía. Toda la operación cross-tenant del platform_owner
          vive acá; el platform_owner NUNCA queda como miembro del tenant. */}
      {session ? (
        <TenantMembersPanel session={session} tenant={tenant} />
      ) : null}
    </Modal>
  );
}
