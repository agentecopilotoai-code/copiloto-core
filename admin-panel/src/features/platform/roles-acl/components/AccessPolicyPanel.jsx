import { Card, CardHeader } from '../../../../components/ui/index.js';
import styles from '../RolesAcl.module.css';

// Static policy notes mirroring the "Política de roles" panel of the HTML
// reference — the server-side access model this matrix is the UI mirror of.
const POLICY_NOTES = [
  {
    title: 'Doble verificación',
    body: 'Cada acción se valida dos veces: una en la sesión del usuario y otra contra la base de datos del negocio. Si los dos chequeos no coinciden, la acción se bloquea automáticamente.',
  },
  {
    title: 'Acceso de plataforma',
    body: 'El platform owner puede operar sobre todos los negocios pero requiere doble factor (MFA) activo y un modo "soporte" auditado que deja registro de cada acción cross-tenant.',
  },
  {
    title: 'Aislamiento entre negocios',
    body: 'El sistema bloquea el alta cruzada: si un usuario ya pertenece a otro negocio, no puede crear uno nuevo con la misma identidad sin pasar por el flujo de invitación.',
  },
  {
    title: 'Matriz como defensa visual',
    body: 'Esta vista oculta y deshabilita los botones según el rol, pero el control real vive en el servidor. Es un espejo informativo del modelo de permisos.',
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
