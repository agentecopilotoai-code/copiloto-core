import { Card, CardHeader } from '../../../../components/ui/index.js';
import styles from '../RolesAcl.module.css';

// Static policy notes mirroring the "Política de roles" panel of the HTML
// reference — the server-side access model this matrix is the UI mirror of.
const POLICY_NOTES = [
  {
    title: 'Doble chequeo obligatorio',
    body: 'El servidor reverifica cada request: el JWT debe portar el rol y la DB debe confirmar la membership del tenant (require_min_role + ensure_tenant_role). JWT-admin + DB-viewer → 403 insufficient_tenant_role (TASK-0077).',
  },
  {
    title: 'Platform unscoped',
    body: 'Un token de platform owner es unscoped: bypassa el tenant scope. Solo opera con MFA verificada y bajo support_mode auditado (TASK-0077 / TASK-0080).',
  },
  {
    title: 'Cross-tenant hijack',
    body: 'El alta cruzada de tenants se bloquea en tenant-signup con 409 si el actor ya tiene una membership previa.',
  },
  {
    title: 'Esta matriz es defensa en profundidad',
    body: 'La UI oculta/deshabilita controles según esta matriz, pero el enforcement real vive en el backend (JWT + role + RLS por endpoint). La matriz nunca reemplaza el chequeo del API.',
  },
];

/**
 * Static "Política de roles" panel — the server-side access-model context the
 * capability × role matrix is the UI mirror of. Read-only informational copy.
 */
export function AccessPolicyPanel() {
  return (
    <Card padding="md">
      <CardHeader
        title="Política de roles"
        subtitle="El modelo de acceso del servidor que esta matriz refleja"
      />
      <dl className={styles.policyGrid}>
        {POLICY_NOTES.map((note) => (
          <div key={note.title} className={styles.policyItem}>
            <dt className={styles.policyTitle}>{note.title}</dt>
            <dd className={styles.policyBody}>{note.body}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
