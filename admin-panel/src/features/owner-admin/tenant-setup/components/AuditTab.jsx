import { Button, Card } from '../../../../components/ui/index.js';
import { formatJson } from '../tenantSetupTransforms.js';
import styles from '../TenantSetupWizard.module.css';

export function AuditTab({ state, actions }) {
  const { auditLogs, lastSettings, isBusy, currentTenantId } = state;
  const { refreshAuditLogs } = actions;

  return (
    <Card padding="md">
      <div className={styles.actions}>
        <Button
          variant="primary"
          disabled={isBusy || !currentTenantId}
          onClick={() => refreshAuditLogs()}
          type="button"
        >
          Refrescar auditoría
        </Button>
      </div>
      {lastSettings ? (
        <div className={styles.builderPreview}>
          <strong>Últimos settings guardados</strong>
          <pre>{formatJson(lastSettings)}</pre>
        </div>
      ) : null}
      <div className={styles.auditList}>
        {auditLogs.length === 0 ? (
          <p className={styles.hint}>Aún no hay logs cargados. Guarda settings o refresca la auditoría.</p>
        ) : null}
        {auditLogs.map((log) => (
          <article className={styles.auditItem} key={log.id}>
            <strong>{log.action}</strong>
            <span>{log.actor_type} · {log.entity_type}</span>
            <small>{log.created_at}</small>
          </article>
        ))}
      </div>
    </Card>
  );
}
