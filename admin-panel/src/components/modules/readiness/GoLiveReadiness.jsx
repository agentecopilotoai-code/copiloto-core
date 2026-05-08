import { useEffect, useState } from 'react';

import { getTenantReadiness } from '../../../services/coreApi.js';

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

export function GoLiveReadiness({ module, session, tenant }) {
  const [report, setReport] = useState(null);
  const [smokeQuestion, setSmokeQuestion] = useState(DEFAULT_SMOKE_QUESTION);
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);

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

  useEffect(() => {
    setReport(null);
    if (tenant?.id) refreshReadiness(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

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
        </>
      ) : (
        <p className="hint">Genera el reporte para validar tenant activo, settings, WhatsApp, knowledge retrieval, handoff y auditoría.</p>
      )}
    </section>
  );
}
