import { formatJson } from '../tenantSetupTransforms.js';

export function AuditTab({ state, actions }) {
  const { auditLogs, lastSettings, isBusy, currentTenantId } = state;
  const { refreshAuditLogs } = actions;

  return (
    <div className="wizard-panel">
      <div className="audit-actions">
        <button className="primary-action" disabled={isBusy || !currentTenantId} onClick={() => refreshAuditLogs()} type="button">Refrescar auditoría</button>
      </div>
      {lastSettings ? <div className="builder-preview"><strong>Últimos settings guardados</strong><pre>{formatJson(lastSettings)}</pre></div> : null}
      <div className="audit-list">
        {auditLogs.length === 0 ? <p className="hint">Aún no hay logs cargados. Guarda settings o refresca la auditoría.</p> : null}
        {auditLogs.map((log) => (
          <article className="audit-item" key={log.id}>
            <strong>{log.action}</strong>
            <span>{log.actor_type} · {log.entity_type}</span>
            <small>{log.created_at}</small>
          </article>
        ))}
      </div>
    </div>
  );
}
