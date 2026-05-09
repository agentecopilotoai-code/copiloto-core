import { useEffect, useState } from 'react';

import { getTenantReadiness, patchWhatsAppChannelMode } from '../../../services/coreApi.js';

const DEFAULT_SMOKE_QUESTION = 'horarios políticas servicios garantías precios contacto';

function readinessBadge(status) {
  return status === 'ready' ? 'Listo' : 'No listo';
}

function CheckItem({ check }) {
  return (
    <article className={`readiness-check ${check.ready ? 'ready' : 'not-ready'}`}>
      <div className="readiness-check-icon" aria-hidden="true">{check.ready ? '✓' : '!'}</div>
      <div>
        <strong>{check.label}</strong>
        <p>{check.reason}</p>
        {check.details ? (
          <small>{Object.entries(check.details).filter(([, value]) => value !== null && value !== undefined && value !== '').slice(0, 4).map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`).join(' · ')}</small>
        ) : null}
      </div>
    </article>
  );
}

function buildEvidenceText(report, tenant) {
  const now = new Date().toISOString();
  const channelCheck = report.checks.find((c) => c.key === 'whatsapp_channel') || {};
  const ragCheck = report.checks.find((c) => c.key === 'knowledge_retrieval') || {};
  const rows = report.checks.map((c) => `| ${c.label.padEnd(30)} | ${c.ready ? '✓' : '✗'}    | ${c.reason} |`).join('\n');

  return `## Evidencia de go-live — ${tenant?.slug || report.tenant_id} (${report.tenant_id})

| Campo           | Valor                          |
|-----------------|--------------------------------|
| Tenant ID       | ${report.tenant_id}            |
| Tenant slug     | ${tenant?.slug || '—'}         |
| Responsable     | (completar)                    |
| Fecha informe   | ${now}                         |
| Resultado       | ${report.ready ? 'APROBADO' : 'BLOQUEADO'} |
| Readiness       | ${report.status}               |
| account_mode    | ${channelCheck.details?.delivery_mode_live ? 'live' : 'mock'} |
| RAG sufficient  | ${ragCheck.details?.sufficient_context ?? '—'} |
| RAG top_score   | ${ragCheck.details?.top_score ?? '—'} |
| Checks ok       | ${report.checks.filter((c) => c.ready).length} |
| Checks fallidos | ${report.checks.filter((c) => !c.ready).length} |

### Checks individuales

| Check                          | Estado | Razón |
|--------------------------------|--------|-------|
${rows}

### Bloqueos

${report.reasons.length ? report.reasons.map((r) => `- ${r}`).join('\n') : 'Ninguno.'}

### Notas del operador

<!-- completar -->

### Rollback ejecutado

<!-- Si se ejecutó rollback: fecha, razón, acción tomada -->
`;
}

export function GoLiveReadiness({ module, session, tenant }) {
  const [report, setReport] = useState(null);
  const [smokeQuestion, setSmokeQuestion] = useState(DEFAULT_SMOKE_QUESTION);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [rollbackReason, setRollbackReason] = useState('');
  const [showRollback, setShowRollback] = useState(false);
  const [rollbackBusy, setRollbackBusy] = useState(false);

  async function refreshReadiness(showNotice = true) {
    if (!tenant?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      const nextReport = await getTenantReadiness(session, tenant.id, { smokeQuestion });
      setReport(nextReport);
      if (showNotice) {
        setNotice({ type: nextReport.ready ? 'success' : 'error', message: nextReport.ready ? 'Tenant listo para go-live controlado.' : 'Tenant no listo: revisa las razones.' });
      }
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'No se pudo generar el checklist de go-live.' });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRollbackToMock() {
    if (!tenant?.id) return;
    const reason = rollbackReason.trim() || 'Rollback preventivo desde Admin Panel';
    setRollbackBusy(true);
    setNotice(null);
    try {
      await patchWhatsAppChannelMode(session, tenant.id, 'mock', reason);
      setNotice({ type: 'success', message: 'Canal WhatsApp cambiado a modo mock. Los mensajes ya no se envían a Meta.' });
      setShowRollback(false);
      setRollbackReason('');
      await refreshReadiness(false);
    } catch (error) {
      setNotice({ type: 'error', message: error.message || 'Error al ejecutar rollback.' });
    } finally {
      setRollbackBusy(false);
    }
  }

  function handleExportEvidence() {
    if (!report) return;
    const text = buildEvidenceText(report, tenant);
    const blob = new Blob([text], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `go-live-evidence-${tenant?.slug || report.tenant_id}-${new Date().toISOString().slice(0, 10)}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => {
    setReport(null);
    if (tenant?.id) refreshReadiness(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  const channelCheck = report?.checks?.find((c) => c.key === 'whatsapp_channel');
  const isLive = channelCheck?.details?.delivery_mode_live;

  return (
    <section className="module-card readiness-module">
      <div className="module-heading">
        <div>
          <p className="eyebrow">Checklist automatizado</p>
          <h2>{module.label}</h2>
          <p>{module.summary}</p>
        </div>
        {report ? <span className={`readiness-badge ${report.status}`}>{readinessBadge(report.status)}</span> : null}
      </div>

      {notice ? <div className={`notice ${notice.type}`}>{notice.message}</div> : null}

      <div className="readiness-controls">
        <label>
          Pregunta de smoke test RAG
          <input value={smokeQuestion} onChange={(event) => setSmokeQuestion(event.target.value)} />
        </label>
        <button className="primary-action" disabled={isBusy || !tenant?.id} onClick={() => refreshReadiness()} type="button">
          {isBusy ? 'Validando…' : 'Generar reporte'}
        </button>
        {report ? (
          <button className="secondary-action" onClick={handleExportEvidence} type="button">
            Exportar evidencia
          </button>
        ) : null}
      </div>

      {report ? (
        <>
          <dl className="context-grid readiness-summary">
            <div>
              <dt>Estado</dt>
              <dd>{readinessBadge(report.status)}</dd>
            </div>
            <div>
              <dt>Tenant</dt>
              <dd>{report.tenant_id}</dd>
            </div>
            <div>
              <dt>Validado en</dt>
              <dd>{new Date(report.checked_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Razones pendientes</dt>
              <dd>{report.reasons.length}</dd>
            </div>
          </dl>

          {report.reasons.length ? (
            <div className="readiness-reasons">
              <strong>Razones de not_ready</strong>
              <ul>
                {report.reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            </div>
          ) : null}

          <div className="readiness-checks">
            {report.checks.map((check) => <CheckItem check={check} key={check.key} />)}
          </div>

          {/* Rollback operativo */}
          <div className="readiness-rollback">
            <button
              className="danger-action"
              onClick={() => setShowRollback((v) => !v)}
              type="button"
            >
              {showRollback ? 'Cancelar rollback' : 'Ejecutar rollback a mock'}
            </button>
            {showRollback ? (
              <div className="rollback-panel">
                <p className="rollback-description">
                  {isLive
                    ? 'El canal está en modo live. Volver a mock detiene el envío real de mensajes a Meta/WhatsApp sin intervención SQL.'
                    : 'El canal ya está en modo mock. Ejecutar rollback lo confirmará con auditoría.'}
                </p>
                <label>
                  Razón del rollback
                  <input
                    placeholder="Ej: Rollback preventivo pre-go-live"
                    value={rollbackReason}
                    onChange={(e) => setRollbackReason(e.target.value)}
                  />
                </label>
                <button
                  className="danger-action"
                  disabled={rollbackBusy || !tenant?.id}
                  onClick={handleRollbackToMock}
                  type="button"
                >
                  {rollbackBusy ? 'Ejecutando rollback…' : 'Confirmar: cambiar a mock'}
                </button>
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <p className="hint">Genera el reporte para validar tenant activo, settings, WhatsApp, knowledge retrieval, handoff y auditoría.</p>
      )}
    </section>
  );
}
